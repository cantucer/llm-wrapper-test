from __future__ import annotations

import json
import time
from json import JSONDecodeError
from typing import Any
from uuid import uuid4

import httpx

from bench.schemas import (
    PromptConfig,
    RequestResult,
    StreamEventModel,
    TargetConfig,
    TestProfile,
)
from bench.utils import (
    approx_token_count,
    build_chat_completions_url,
    build_models_url,
    json_dumps,
    redact_headers,
    safe_percentile,
    utc_now,
)


REQUEST_ID_HEADERS = [
    "x-request-id",
    "x-litellm-call-id",
    "x-bifrost-request-id",
    "openai-request-id",
]


def build_headers(
    target: TargetConfig,
    client_request_id: str,
    extra_headers: dict[str, str] | None = None,
) -> dict[str, str]:
    headers = {
        "Content-Type": "application/json",
        "x-client-request-id": client_request_id,
        **target.headers,
    }
    api_key = target.api_key_value()
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    if extra_headers:
        headers.update(extra_headers)
    return headers


def build_chat_payload(
    target: TargetConfig,
    prompt: PromptConfig,
    profile: TestProfile,
    *,
    stream: bool,
    override_model: str | None = None,
    extra_body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": override_model or target.model,
        "messages": prompt.expanded_messages(),
        "temperature": profile.temperature,
        "top_p": profile.top_p,
        "max_tokens": profile.max_tokens,
        "stream": stream,
    }
    if stream:
        payload["stream_options"] = {"include_usage": True}
    if target.extra_body:
        payload.update(target.extra_body)
    if extra_body:
        payload.update(extra_body)
    return payload


def extract_provider_request_id(
    response_headers: dict[str, str], provider_json_id: str | None = None
) -> str | None:
    normalized_headers = {key.lower(): value for key, value in response_headers.items()}
    for header_name in REQUEST_ID_HEADERS:
        value = normalized_headers.get(header_name)
        if value:
            return value
    return provider_json_id


def _base_result(
    *,
    run_id: str,
    target: TargetConfig,
    prompt: PromptConfig,
    profile: TestProfile,
    client_request_id: str,
    concurrency_level: int,
    repetition_index: int,
    request_started_at,
) -> RequestResult:
    return RequestResult(
        run_id=run_id,
        target_id=target.id,
        target_name=target.name,
        prompt_id=prompt.id,
        prompt_category=prompt.category,
        concurrency_level=concurrency_level,
        repetition_index=repetition_index,
        request_started_at=request_started_at,
        request_finished_at=None,
        status="error",
        client_request_id=client_request_id,
        model=target.model,
        base_url=target.base_url or "",
        stream=profile.stream,
        temperature=profile.temperature,
        top_p=profile.top_p,
        max_tokens=profile.max_tokens,
        prompt_chars=prompt.prompt_chars(),
    )


def _finish_error(
    result: RequestResult,
    *,
    error_type: str,
    error_message: str,
    start_time: float,
    http_status_code: int | None = None,
    response_headers: dict[str, str] | None = None,
    provider_json_id: str | None = None,
    output_text: str | None = None,
) -> RequestResult:
    result.request_finished_at = utc_now()
    result.total_latency_ms = (time.perf_counter() - start_time) * 1000
    result.status = "timeout" if error_type == "timeout" else "error"
    result.error_type = error_type
    result.error_message = error_message[:4000]
    result.http_status_code = http_status_code
    if response_headers:
        result.response_headers_json = json_dumps(dict(response_headers))
        result.provider_request_id = extract_provider_request_id(
            response_headers, provider_json_id
        )
    if output_text:
        result.output_text = output_text
        result.output_chars = len(output_text)
        result.approx_output_tokens = approx_token_count(output_text)
    return result


def _usage_fields(usage: dict[str, Any] | None) -> dict[str, Any]:
    if not usage:
        return {}
    return {
        "prompt_tokens_reported": usage.get("prompt_tokens"),
        "completion_tokens_reported": usage.get("completion_tokens"),
        "total_tokens_reported": usage.get("total_tokens"),
        "raw_usage_json": json_dumps(usage),
    }


def _tokens_per_second(tokens: int | None, latency_ms: float | None) -> float | None:
    if not tokens or not latency_ms or latency_ms <= 0:
        return None
    return float(tokens / (latency_ms / 1000))


async def run_streaming_chat_completion(
    target: TargetConfig,
    prompt: PromptConfig,
    profile: TestProfile,
    client_request_id: str,
    *,
    run_id: str = "",
    concurrency_level: int = 1,
    repetition_index: int = 0,
    override_model: str | None = None,
    extra_body: dict[str, Any] | None = None,
    extra_headers: dict[str, str] | None = None,
    timeout_override: float | None = None,
) -> tuple[RequestResult, list[StreamEventModel]]:
    request_started_at = utc_now()
    start_time = time.perf_counter()
    result = _base_result(
        run_id=run_id,
        target=target,
        prompt=prompt,
        profile=profile,
        client_request_id=client_request_id,
        concurrency_level=concurrency_level,
        repetition_index=repetition_index,
        request_started_at=request_started_at,
    )
    result.stream = True
    url = build_chat_completions_url(target.base_url, target.chat_endpoint_path)
    payload = build_chat_payload(
        target,
        prompt,
        profile,
        stream=True,
        override_model=override_model,
        extra_body=extra_body,
    )
    headers = build_headers(target, client_request_id, extra_headers)
    result.extra_json = json_dumps(
        {
            "request_url": url,
            "request_headers_redacted": redact_headers(headers),
            "request_header_names": list(headers.keys()),
            "target_mode": target.mode,
            "target_kind": target.kind,
        }
    )
    timeout = httpx.Timeout(timeout_override or profile.timeout_sec)

    stream_events: list[StreamEventModel] = []
    event_index = 0
    content_chunks: list[str] = []
    content_chunk_times: list[float] = []
    usage: dict[str, Any] | None = None
    provider_json_id: str | None = None
    response_headers: dict[str, str] = {}

    try:
        async with httpx.AsyncClient(
            timeout=timeout, verify=target.ssl_verify_value()
        ) as client:
            async with client.stream(
                "POST", url, json=payload, headers=headers
            ) as response:
                response_headers = dict(response.headers)
                result.http_status_code = response.status_code
                result.response_headers_json = json_dumps(response_headers)
                if response.status_code >= 400:
                    body = (await response.aread()).decode("utf-8", errors="replace")
                    return (
                        _finish_error(
                            result,
                            error_type="http_error",
                            error_message=body or response.reason_phrase,
                            start_time=start_time,
                            http_status_code=response.status_code,
                            response_headers=response_headers,
                        ),
                        stream_events,
                    )

                async for line in response.aiter_lines():
                    if not line:
                        continue
                    if not line.startswith("data:"):
                        continue
                    elapsed_ms = (time.perf_counter() - start_time) * 1000
                    if result.first_chunk_ms is None:
                        result.first_chunk_ms = elapsed_ms
                    payload_text = line[len("data:") :].strip()
                    if payload_text == "[DONE]":
                        if profile.store_stream_events:
                            stream_events.append(
                                StreamEventModel(
                                    request_result_id=result.id,
                                    event_index=event_index,
                                    elapsed_ms=elapsed_ms,
                                    event_type="done",
                                )
                            )
                        break
                    event_index += 1
                    result.chunk_count += 1
                    try:
                        event_json = json.loads(payload_text)
                    except JSONDecodeError as exc:
                        return (
                            _finish_error(
                                result,
                                error_type="sse_parse_error",
                                error_message=f"Malformed SSE JSON: {exc}",
                                start_time=start_time,
                                http_status_code=response.status_code,
                                response_headers=response_headers,
                                output_text="".join(content_chunks),
                            ),
                            stream_events,
                        )

                    provider_json_id = event_json.get("id") or provider_json_id
                    usage = event_json.get("usage") or usage
                    choices = event_json.get("choices") or []
                    delta_text = ""
                    if choices:
                        delta = choices[0].get("delta") or {}
                        delta_text = delta.get("content") or ""
                    if delta_text:
                        if result.first_content_chunk_ms is None:
                            result.first_content_chunk_ms = elapsed_ms
                        result.content_chunk_count += 1
                        result.time_to_last_token_ms = elapsed_ms
                        content_chunk_times.append(elapsed_ms)
                        content_chunks.append(delta_text)
                    if profile.store_stream_events:
                        stream_events.append(
                            StreamEventModel(
                                request_result_id=result.id,
                                event_index=event_index,
                                elapsed_ms=elapsed_ms,
                                event_type="content" if delta_text else "metadata",
                                delta_text=delta_text or None,
                                raw_event_json=json_dumps(event_json),
                            )
                        )
    except httpx.TimeoutException as exc:
        return (
            _finish_error(
                result,
                error_type="timeout",
                error_message=str(exc) or "request timed out",
                start_time=start_time,
                response_headers=response_headers,
                output_text="".join(content_chunks),
            ),
            stream_events,
        )
    except httpx.ConnectError as exc:
        return (
            _finish_error(
                result,
                error_type="connection_error",
                error_message=str(exc),
                start_time=start_time,
                response_headers=response_headers,
                output_text="".join(content_chunks),
            ),
            stream_events,
        )
    except httpx.HTTPError as exc:
        return (
            _finish_error(
                result,
                error_type="http_client_error",
                error_message=str(exc),
                start_time=start_time,
                response_headers=response_headers,
                output_text="".join(content_chunks),
            ),
            stream_events,
        )
    except Exception as exc:
        return (
            _finish_error(
                result,
                error_type="unknown_error",
                error_message=str(exc),
                start_time=start_time,
                response_headers=response_headers,
                output_text="".join(content_chunks),
            ),
            stream_events,
        )

    output_text = "".join(content_chunks)
    end_time = time.perf_counter()
    result.request_finished_at = utc_now()
    result.total_latency_ms = (end_time - start_time) * 1000
    result.ttft_ms = result.first_content_chunk_ms
    result.output_text = output_text if profile.store_response_text else None
    result.output_chars = len(output_text)
    result.approx_output_tokens = approx_token_count(output_text)
    result.provider_request_id = extract_provider_request_id(
        response_headers, provider_json_id
    )

    if usage:
        for key, value in _usage_fields(usage).items():
            setattr(result, key, value)
        result.tokens_per_second_reported = _tokens_per_second(
            result.completion_tokens_reported, result.total_latency_ms
        )
    result.tokens_per_second_approx = _tokens_per_second(
        result.approx_output_tokens, result.total_latency_ms
    )

    inter_chunk_deltas = [
        content_chunk_times[index] - content_chunk_times[index - 1]
        for index in range(1, len(content_chunk_times))
    ]
    if inter_chunk_deltas:
        result.mean_inter_content_chunk_ms = float(
            sum(inter_chunk_deltas) / len(inter_chunk_deltas)
        )
        result.p50_inter_content_chunk_ms = safe_percentile(inter_chunk_deltas, 50)
        result.p95_inter_content_chunk_ms = safe_percentile(inter_chunk_deltas, 95)

    if not output_text:
        return (
            _finish_error(
                result,
                error_type="empty_response",
                error_message="stream completed without generated content",
                start_time=start_time,
                http_status_code=result.http_status_code,
                response_headers=response_headers,
                provider_json_id=provider_json_id,
            ),
            stream_events,
        )

    result.status = "success"
    return result, stream_events


async def run_non_streaming_chat_completion(
    target: TargetConfig,
    prompt: PromptConfig,
    profile: TestProfile,
    client_request_id: str,
    *,
    run_id: str = "",
    concurrency_level: int = 1,
    repetition_index: int = 0,
    override_model: str | None = None,
    extra_body: dict[str, Any] | None = None,
    extra_headers: dict[str, str] | None = None,
    timeout_override: float | None = None,
) -> tuple[RequestResult, list[StreamEventModel]]:
    request_started_at = utc_now()
    start_time = time.perf_counter()
    result = _base_result(
        run_id=run_id,
        target=target,
        prompt=prompt,
        profile=profile,
        client_request_id=client_request_id,
        concurrency_level=concurrency_level,
        repetition_index=repetition_index,
        request_started_at=request_started_at,
    )
    result.stream = False
    url = build_chat_completions_url(target.base_url, target.chat_endpoint_path)
    payload = build_chat_payload(
        target,
        prompt,
        profile,
        stream=False,
        override_model=override_model,
        extra_body=extra_body,
    )
    headers = build_headers(target, client_request_id, extra_headers)
    result.extra_json = json_dumps(
        {
            "request_url": url,
            "request_headers_redacted": redact_headers(headers),
            "request_header_names": list(headers.keys()),
            "target_mode": target.mode,
            "target_kind": target.kind,
        }
    )
    timeout = httpx.Timeout(timeout_override or profile.timeout_sec)

    try:
        async with httpx.AsyncClient(
            timeout=timeout, verify=target.ssl_verify_value()
        ) as client:
            response = await client.post(url, json=payload, headers=headers)
            response_headers = dict(response.headers)
            result.http_status_code = response.status_code
            result.response_headers_json = json_dumps(response_headers)
            result.request_finished_at = utc_now()
            result.total_latency_ms = (time.perf_counter() - start_time) * 1000
            if response.status_code >= 400:
                return (
                    _finish_error(
                        result,
                        error_type="http_error",
                        error_message=response.text or response.reason_phrase,
                        start_time=start_time,
                        http_status_code=response.status_code,
                        response_headers=response_headers,
                    ),
                    [],
                )
            data = response.json()
    except httpx.TimeoutException as exc:
        return (
            _finish_error(
                result,
                error_type="timeout",
                error_message=str(exc) or "request timed out",
                start_time=start_time,
            ),
            [],
        )
    except httpx.ConnectError as exc:
        return (
            _finish_error(
                result,
                error_type="connection_error",
                error_message=str(exc),
                start_time=start_time,
            ),
            [],
        )
    except (httpx.HTTPError, JSONDecodeError, ValueError) as exc:
        return (
            _finish_error(
                result,
                error_type="http_client_error",
                error_message=str(exc),
                start_time=start_time,
            ),
            [],
        )

    choices = data.get("choices") or []
    output_text = ""
    if choices:
        message = choices[0].get("message") or {}
        output_text = message.get("content") or ""
    usage = data.get("usage")
    result.provider_request_id = extract_provider_request_id(
        dict(response.headers), data.get("id")
    )
    result.output_text = output_text if profile.store_response_text else None
    result.output_chars = len(output_text)
    result.approx_output_tokens = approx_token_count(output_text)
    result.tokens_per_second_approx = _tokens_per_second(
        result.approx_output_tokens, result.total_latency_ms
    )
    if usage:
        for key, value in _usage_fields(usage).items():
            setattr(result, key, value)
        result.tokens_per_second_reported = _tokens_per_second(
            result.completion_tokens_reported, result.total_latency_ms
        )
    result.extra_json = json_dumps(
        {
            "response_id": data.get("id"),
            "request_url": url,
            "request_headers_redacted": redact_headers(headers),
            "request_header_names": list(headers.keys()),
            "target_mode": target.mode,
            "target_kind": target.kind,
        }
    )

    if not output_text:
        return (
            _finish_error(
                result,
                error_type="empty_response",
                error_message="response completed without generated content",
                start_time=start_time,
                http_status_code=response.status_code,
                response_headers=dict(response.headers),
                provider_json_id=data.get("id"),
            ),
            [],
        )

    result.status = "success"
    return result, []


async def get_models(
    target: TargetConfig, timeout_sec: float = 30
) -> tuple[int | None, dict[str, Any] | None, str | None, float | None]:
    if not target.models_endpoint_supported:
        return None, None, "models endpoint disabled for target", None
    client_request_id = str(uuid4())
    headers = build_headers(target, client_request_id)
    start_time = time.perf_counter()
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_sec), verify=target.ssl_verify_value()
        ) as client:
            response = await client.get(build_models_url(target.base_url), headers=headers)
            latency_ms = (time.perf_counter() - start_time) * 1000
            try:
                body = response.json()
            except ValueError:
                body = {"text": response.text[:2000]}
            return response.status_code, body, None, latency_ms
    except Exception as exc:
        latency_ms = (time.perf_counter() - start_time) * 1000
        return None, None, str(exc), latency_ms
