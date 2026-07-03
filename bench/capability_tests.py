from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

from bench.adapters import get_adapter
from bench.db import insert_capability_result
from bench.http_client import get_models
from bench.schemas import CapabilityResult, PromptConfig, TargetConfig, TestProfile
from bench.utils import json_dumps


CLIENT_API_TESTS = [
    "models",
    "basic_chat",
    "streaming_chat",
    "stream_options.include_usage",
    "system_prompt",
    "long_prompt",
    "bad_model_error",
    "timeout_behavior",
    "extra_body_passthrough",
    "custom_headers_sent",
]

GATEWAY_SERVICE_FEATURES = [
    "virtual_keys",
    "provider_key_management",
    "logging_dashboard",
    "prompt_redaction",
    "response_redaction",
    "cost_tracking",
    "token_tracking",
    "rate_limiting",
    "fallback",
    "load_balancing",
    "caching",
    "prometheus",
    "opentelemetry",
    "request_id_correlation",
]

CAPABILITY_GROUPS = {
    "Client/API compatibility": CLIENT_API_TESTS,
    "Gateway/service features": GATEWAY_SERVICE_FEATURES,
}

CAPABILITY_TESTS = CLIENT_API_TESTS + GATEWAY_SERVICE_FEATURES


def _capability_profile(
    *, stream: bool = False, timeout_sec: int = 30, max_tokens: int = 64
) -> TestProfile:
    return TestProfile(
        name="capability",
        repetitions_per_prompt=1,
        concurrency_levels=[1],
        max_tokens=max_tokens,
        temperature=0.0,
        top_p=1.0,
        timeout_sec=timeout_sec,
        stream=stream,
        store_response_text=True,
        store_stream_events=False,
    )


def _simple_prompt(user: str, system: str = "You are a concise assistant.") -> PromptConfig:
    return PromptConfig(
        id="capability_prompt",
        category="capability",
        description=None,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )


def _manual_gateway_feature(target: TargetConfig, run_id: str | None, test_name: str) -> CapabilityResult:
    return CapabilityResult(
        run_id=run_id,
        target_id=target.id,
        capability_name=test_name,
        status="manual",
        details="Gateway/service feature requires dashboard, logs, metrics, or external configuration evidence.",
    )


def _skip_if_manual(target: TargetConfig, run_id: str | None, test_name: str) -> CapabilityResult | None:
    if target.mode == "manual_only":
        return CapabilityResult(
            run_id=run_id,
            target_id=target.id,
            capability_name=test_name,
            status="manual",
            details="Manual-only target cannot be tested automatically.",
        )
    return None


async def _run_models(target: TargetConfig, run_id: str | None) -> CapabilityResult:
    skipped = _skip_if_manual(target, run_id, "models")
    if skipped:
        return skipped
    if target.mode == "python_sdk":
        return CapabilityResult(
            run_id=run_id,
            target_id=target.id,
            capability_name="models",
            status="not_applicable",
            details="/models is an HTTP gateway capability, not a Python SDK import check.",
        )
    status_code, body, error, latency_ms = await get_models(target)
    if error and not target.models_endpoint_supported:
        status = "not_applicable"
        details = error
    elif error:
        status = "fail"
        details = error
    elif status_code == 200 and isinstance(body, dict) and "data" in body:
        status = "pass"
        details = f"Returned {len(body.get('data') or [])} models."
    elif status_code == 200:
        status = "partial"
        details = "HTTP 200, but response did not include a standard data list."
    else:
        status = "fail"
        details = f"HTTP {status_code}"
    return CapabilityResult(
        run_id=run_id,
        target_id=target.id,
        capability_name="models",
        status=status,
        details=details,
        latency_ms=latency_ms,
        raw_json=json_dumps(body),
    )


async def _run_basic_chat(target: TargetConfig, run_id: str | None) -> CapabilityResult:
    skipped = _skip_if_manual(target, run_id, "basic_chat")
    if skipped:
        return skipped
    result, _ = await get_adapter(target).run_non_streaming_chat(
        target,
        _simple_prompt("Reply with exactly: ok"),
        _capability_profile(stream=False),
        str(uuid4()),
        run_id=run_id or "",
    )
    return CapabilityResult(
        run_id=run_id,
        target_id=target.id,
        capability_name="basic_chat",
        status="pass" if result.status == "success" else "fail",
        details=result.error_message or f"Output chars: {result.output_chars}",
        latency_ms=result.total_latency_ms,
        raw_json=result.model_dump_json(),
    )


async def _run_streaming_chat(target: TargetConfig, run_id: str | None) -> CapabilityResult:
    skipped = _skip_if_manual(target, run_id, "streaming_chat")
    if skipped:
        return skipped
    result, _ = await get_adapter(target).run_streaming_chat(
        target,
        _simple_prompt("Reply with a short sentence."),
        _capability_profile(stream=True),
        str(uuid4()),
        run_id=run_id or "",
    )
    return CapabilityResult(
        run_id=run_id,
        target_id=target.id,
        capability_name="streaming_chat",
        status="pass" if result.status == "success" and result.content_chunk_count else "fail",
        details=result.error_message or f"Content chunks: {result.content_chunk_count}",
        latency_ms=result.total_latency_ms,
        raw_json=result.model_dump_json(),
    )


async def _run_system_prompt(target: TargetConfig, run_id: str | None) -> CapabilityResult:
    skipped = _skip_if_manual(target, run_id, "system_prompt")
    if skipped:
        return skipped
    prompt = _simple_prompt(
        "What is 2 + 2?",
        system="You must answer using the exact prefix SYSTEM_OK:",
    )
    result, _ = await get_adapter(target).run_non_streaming_chat(
        target, prompt, _capability_profile(stream=False), str(uuid4()), run_id=run_id or ""
    )
    output = result.output_text or ""
    if result.status != "success":
        status = "fail"
    elif "SYSTEM_OK:" in output:
        status = "pass"
    else:
        status = "partial"
    return CapabilityResult(
        run_id=run_id,
        target_id=target.id,
        capability_name="system_prompt",
        status=status,
        details=result.error_message or output[:500],
        latency_ms=result.total_latency_ms,
        raw_json=result.model_dump_json(),
    )


async def _run_long_prompt(target: TargetConfig, run_id: str | None) -> CapabilityResult:
    skipped = _skip_if_manual(target, run_id, "long_prompt")
    if skipped:
        return skipped
    prompt = PromptConfig(
        id="long_capability_prompt",
        category="capability",
        description=None,
        repeat_user_content=80,
        messages=[
            {"role": "system", "content": "You summarize technical text."},
            {
                "role": "user",
                "content": "Summarize this sentence: LLM gateways route, log, limit, and observe requests.",
            },
        ],
    )
    result, _ = await get_adapter(target).run_non_streaming_chat(
        target,
        prompt,
        _capability_profile(stream=False, timeout_sec=60, max_tokens=128),
        str(uuid4()),
        run_id=run_id or "",
    )
    return CapabilityResult(
        run_id=run_id,
        target_id=target.id,
        capability_name="long_prompt",
        status="pass" if result.status == "success" else "fail",
        details=result.error_message or f"Prompt chars: {result.prompt_chars}",
        latency_ms=result.total_latency_ms,
        raw_json=result.model_dump_json(),
    )


async def _run_bad_model_error(target: TargetConfig, run_id: str | None) -> CapabilityResult:
    skipped = _skip_if_manual(target, run_id, "bad_model_error")
    if skipped:
        return skipped
    if target.mode == "python_sdk":
        return CapabilityResult(
            run_id=run_id,
            target_id=target.id,
            capability_name="bad_model_error",
            status="skip",
            details="Bad-model shape varies by SDK and provider; test via HTTP gateway target when possible.",
        )
    from bench.http_client import run_non_streaming_chat_completion

    result, _ = await run_non_streaming_chat_completion(
        target,
        _simple_prompt("Hello"),
        _capability_profile(stream=False),
        str(uuid4()),
        run_id=run_id or "",
        override_model="__missing_model_for_wrapper_benchmark__",
    )
    if result.http_status_code and 400 <= result.http_status_code < 500:
        status = "pass"
    elif result.status == "error":
        status = "partial"
    else:
        status = "fail"
    return CapabilityResult(
        run_id=run_id,
        target_id=target.id,
        capability_name="bad_model_error",
        status=status,
        details=result.error_message or f"HTTP {result.http_status_code}",
        latency_ms=result.total_latency_ms,
        raw_json=result.model_dump_json(),
    )


async def _run_timeout_behavior(target: TargetConfig, run_id: str | None) -> CapabilityResult:
    skipped = _skip_if_manual(target, run_id, "timeout_behavior")
    if skipped:
        return skipped
    if target.mode == "python_sdk":
        return CapabilityResult(
            run_id=run_id,
            target_id=target.id,
            capability_name="timeout_behavior",
            status="skip",
            details="Timeout behavior is measured through HTTP gateways in this version.",
        )
    from bench.http_client import run_non_streaming_chat_completion

    result, _ = await run_non_streaming_chat_completion(
        target,
        _simple_prompt("Write one paragraph."),
        _capability_profile(stream=False, timeout_sec=1, max_tokens=256),
        str(uuid4()),
        run_id=run_id or "",
        timeout_override=0.001,
    )
    return CapabilityResult(
        run_id=run_id,
        target_id=target.id,
        capability_name="timeout_behavior",
        status="pass" if result.status == "timeout" else "partial",
        details=result.error_message or f"Status: {result.status}",
        latency_ms=result.total_latency_ms,
        raw_json=result.model_dump_json(),
    )


async def _run_extra_body_passthrough(target: TargetConfig, run_id: str | None) -> CapabilityResult:
    skipped = _skip_if_manual(target, run_id, "extra_body_passthrough")
    if skipped:
        return skipped
    if target.mode == "python_sdk":
        return CapabilityResult(
            run_id=run_id,
            target_id=target.id,
            capability_name="extra_body_passthrough",
            status="skip",
            details="Extra body passthrough is an HTTP payload compatibility test.",
        )
    from bench.http_client import run_non_streaming_chat_completion

    result, _ = await run_non_streaming_chat_completion(
        target,
        _simple_prompt("Reply with one word."),
        _capability_profile(stream=False),
        str(uuid4()),
        run_id=run_id or "",
        extra_body={"top_k": -1},
    )
    if result.status == "success":
        status = "pass"
    elif result.http_status_code and 400 <= result.http_status_code < 500:
        status = "partial"
    else:
        status = "fail"
    return CapabilityResult(
        run_id=run_id,
        target_id=target.id,
        capability_name="extra_body_passthrough",
        status=status,
        details=result.error_message or "Sent top_k=-1 in request body.",
        latency_ms=result.total_latency_ms,
        raw_json=result.model_dump_json(),
    )


async def _run_custom_headers_sent(target: TargetConfig, run_id: str | None) -> CapabilityResult:
    skipped = _skip_if_manual(target, run_id, "custom_headers_sent")
    if skipped:
        return skipped
    if target.mode == "python_sdk":
        return CapabilityResult(
            run_id=run_id,
            target_id=target.id,
            capability_name="custom_headers_sent",
            status="not_applicable",
            details="Custom HTTP headers are not applicable to in-process SDK calls.",
        )
    start = time.perf_counter()
    from bench.http_client import run_non_streaming_chat_completion

    result, _ = await run_non_streaming_chat_completion(
        target,
        _simple_prompt("Reply with ok."),
        _capability_profile(stream=False),
        str(uuid4()),
        run_id=run_id or "",
        extra_headers={"x-client-request-id": f"bench-{uuid4()}"},
    )
    latency_ms = (time.perf_counter() - start) * 1000
    if result.status == "success":
        status = "partial"
        details = "Client sent configured headers; verify gateway receipt in logs."
    else:
        status = "fail"
        details = result.error_message
    return CapabilityResult(
        run_id=run_id,
        target_id=target.id,
        capability_name="custom_headers_sent",
        status=status,
        details=details,
        latency_ms=latency_ms,
        raw_json=result.model_dump_json(),
    )


async def _run_stream_usage(target: TargetConfig, run_id: str | None) -> CapabilityResult:
    skipped = _skip_if_manual(target, run_id, "stream_options.include_usage")
    if skipped:
        return skipped
    if target.mode == "python_sdk":
        return CapabilityResult(
            run_id=run_id,
            target_id=target.id,
            capability_name="stream_options.include_usage",
            status="skip",
            details="Stream usage object is tested through HTTP gateways in this version.",
        )
    result, _ = await get_adapter(target).run_streaming_chat(
        target,
        _simple_prompt("Reply with a short sentence."),
        _capability_profile(stream=True),
        str(uuid4()),
        run_id=run_id or "",
    )
    if result.raw_usage_json:
        status = "pass"
        details = "Stream included usage object."
    elif result.status == "success":
        status = "partial"
        details = "Streaming worked, but usage was not included."
    else:
        status = "fail"
        details = result.error_message
    return CapabilityResult(
        run_id=run_id,
        target_id=target.id,
        capability_name="stream_options.include_usage",
        status=status,
        details=details,
        latency_ms=result.total_latency_ms,
        raw_json=result.model_dump_json(),
    )


RUNNERS = {
    "models": _run_models,
    "basic_chat": _run_basic_chat,
    "streaming_chat": _run_streaming_chat,
    "system_prompt": _run_system_prompt,
    "long_prompt": _run_long_prompt,
    "bad_model_error": _run_bad_model_error,
    "timeout_behavior": _run_timeout_behavior,
    "extra_body_passthrough": _run_extra_body_passthrough,
    "custom_headers_sent": _run_custom_headers_sent,
    "stream_options.include_usage": _run_stream_usage,
}


async def run_capability_tests(
    targets: list[TargetConfig],
    selected_tests: list[str] | None = None,
    *,
    run_id: str | None = None,
    db_path: str | Path | None = None,
) -> list[CapabilityResult]:
    selected = selected_tests or CAPABILITY_TESTS
    results: list[CapabilityResult] = []
    for target in targets:
        for test_name in selected:
            runner = RUNNERS.get(test_name)
            if not runner and test_name in GATEWAY_SERVICE_FEATURES:
                result = _manual_gateway_feature(target, run_id, test_name)
            elif not runner:
                result = CapabilityResult(
                    run_id=run_id,
                    target_id=target.id,
                    capability_name=test_name,
                    status="skip",
                    details="Unknown capability test.",
                )
            else:
                result = await runner(target, run_id)
            insert_capability_result(result, db_path)
            results.append(result)
            await asyncio.sleep(0)
    return results


async def check_target_health(target: TargetConfig) -> dict[str, Any]:
    result = await get_adapter(target).healthcheck(target)
    return result.model_dump()
