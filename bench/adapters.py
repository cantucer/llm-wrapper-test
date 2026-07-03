from __future__ import annotations

import time
from typing import Protocol
from uuid import uuid4

from bench.http_client import (
    get_models,
    run_non_streaming_chat_completion,
    run_streaming_chat_completion,
)
from bench.schemas import (
    HealthcheckResult,
    PromptConfig,
    RequestResult,
    StreamEventModel,
    TargetConfig,
    TestProfile,
)
from bench.utils import (
    approx_token_count,
    generate_curl_test_command,
    json_dumps,
    safe_percentile,
    utc_now,
)


class TargetAdapter(Protocol):
    async def healthcheck(self, target: TargetConfig) -> HealthcheckResult:
        ...

    async def run_streaming_chat(
        self,
        target: TargetConfig,
        prompt: PromptConfig,
        profile: TestProfile,
        client_request_id: str,
        *,
        run_id: str = "",
        concurrency_level: int = 1,
        repetition_index: int = 0,
    ) -> tuple[RequestResult, list[StreamEventModel]]:
        ...

    async def run_non_streaming_chat(
        self,
        target: TargetConfig,
        prompt: PromptConfig,
        profile: TestProfile,
        client_request_id: str,
        *,
        run_id: str = "",
        concurrency_level: int = 1,
        repetition_index: int = 0,
    ) -> tuple[RequestResult, list[StreamEventModel]]:
        ...


def _manual_result(
    target: TargetConfig,
    prompt: PromptConfig,
    profile: TestProfile,
    client_request_id: str,
    *,
    run_id: str,
    concurrency_level: int,
    repetition_index: int,
    error_type: str,
    error_message: str,
) -> RequestResult:
    now = utc_now()
    return RequestResult(
        run_id=run_id,
        target_id=target.id,
        target_name=target.name,
        prompt_id=prompt.id,
        prompt_category=prompt.category,
        concurrency_level=concurrency_level,
        repetition_index=repetition_index,
        request_started_at=now,
        request_finished_at=now,
        status="error",
        error_type=error_type,
        error_message=error_message,
        client_request_id=client_request_id,
        model=target.model,
        base_url=target.base_url or "",
        stream=profile.stream,
        temperature=profile.temperature,
        top_p=profile.top_p,
        max_tokens=profile.max_tokens,
        prompt_chars=prompt.prompt_chars(),
        extra_json=json_dumps({"target_mode": target.mode, "target_kind": target.kind}),
    )


class OpenAIHTTPAdapter:
    async def healthcheck(self, target: TargetConfig) -> HealthcheckResult:
        if not target.healthcheck_enabled:
            return HealthcheckResult(
                target_id=target.id,
                target_name=target.name,
                mode=target.mode,
                base_url=target.base_url,
                model=target.model,
                api_key_env=target.api_key_env,
                api_key_env_exists=bool(target.api_key_value()),
                setup_required=target.setup_required,
                status_color="gray",
                details="Healthcheck disabled for this target.",
                curl_command=generate_curl_test_command(target) if target.base_url else None,
                setup_doc_section=target.setup_doc_section,
                setup_notes=target.notes,
            )

        models_status, models_body, models_error, _ = await get_models(target)
        chat_result, _ = await run_non_streaming_chat_completion(
            target,
            PromptConfig(
                id="healthcheck_basic",
                category="healthcheck",
                messages=[{"role": "user", "content": "Say OK"}],
            ),
            TestProfile(
                name="healthcheck",
                repetitions_per_prompt=1,
                concurrency_levels=[1],
                max_tokens=16,
                temperature=0,
                top_p=1,
                timeout_sec=30,
                stream=False,
                store_response_text=True,
            ),
            str(uuid4()),
        )
        streaming_result, _ = await run_streaming_chat_completion(
            target,
            PromptConfig(
                id="healthcheck_streaming",
                category="healthcheck",
                messages=[{"role": "user", "content": "Say OK"}],
            ),
            TestProfile(
                name="healthcheck",
                repetitions_per_prompt=1,
                concurrency_levels=[1],
                max_tokens=16,
                temperature=0,
                top_p=1,
                timeout_sec=30,
                stream=True,
                store_response_text=True,
            ),
            str(uuid4()),
        )
        discovered_models = []
        if isinstance(models_body, dict):
            for model in models_body.get("data") or []:
                if isinstance(model, dict) and model.get("id"):
                    discovered_models.append(str(model["id"]))

        models_works = (
            None
            if not target.models_endpoint_supported
            else models_status is not None and 200 <= models_status < 300
        )
        chat_works = chat_result.status == "success"
        streaming_works = streaming_result.status == "success"
        service_reachable = bool(models_works or chat_works or streaming_works)
        if chat_works and streaming_works and (models_works or models_works is None):
            color = "green"
        elif service_reachable:
            color = "yellow"
        else:
            color = "red"

        details = []
        if models_error:
            details.append(f"/models: {models_error}")
        if chat_result.error_message:
            details.append(f"chat: {chat_result.error_message}")
        if streaming_result.error_message:
            details.append(f"streaming: {streaming_result.error_message}")

        return HealthcheckResult(
            target_id=target.id,
            target_name=target.name,
            mode=target.mode,
            base_url=target.base_url,
            model=target.model,
            api_key_env=target.api_key_env,
            api_key_env_exists=bool(target.api_key_value()),
            setup_required=target.setup_required,
            service_reachable=service_reachable,
            models_works=models_works,
            chat_works=chat_works,
            streaming_works=streaming_works,
            status_color=color,
            details="; ".join(details) or None,
            models_status_code=models_status,
            chat_status_code=chat_result.http_status_code,
            streaming_status_code=streaming_result.http_status_code,
            discovered_models=discovered_models,
            curl_command=generate_curl_test_command(target) if target.base_url else None,
            setup_doc_section=target.setup_doc_section,
            setup_notes=target.notes,
        )

    async def run_streaming_chat(
        self,
        target: TargetConfig,
        prompt: PromptConfig,
        profile: TestProfile,
        client_request_id: str,
        *,
        run_id: str = "",
        concurrency_level: int = 1,
        repetition_index: int = 0,
    ) -> tuple[RequestResult, list[StreamEventModel]]:
        return await run_streaming_chat_completion(
            target,
            prompt,
            profile,
            client_request_id,
            run_id=run_id,
            concurrency_level=concurrency_level,
            repetition_index=repetition_index,
        )

    async def run_non_streaming_chat(
        self,
        target: TargetConfig,
        prompt: PromptConfig,
        profile: TestProfile,
        client_request_id: str,
        *,
        run_id: str = "",
        concurrency_level: int = 1,
        repetition_index: int = 0,
    ) -> tuple[RequestResult, list[StreamEventModel]]:
        return await run_non_streaming_chat_completion(
            target,
            prompt,
            profile,
            client_request_id,
            run_id=run_id,
            concurrency_level=concurrency_level,
            repetition_index=repetition_index,
        )


class LiteLLMSDKAdapter:
    def _import_litellm(self):
        try:
            import litellm  # type: ignore[import-not-found]
        except ImportError as exc:
            raise RuntimeError(
                "LiteLLM SDK target selected, but the litellm package is not installed."
            ) from exc
        return litellm

    async def healthcheck(self, target: TargetConfig) -> HealthcheckResult:
        try:
            await self._call_litellm(
                target,
                PromptConfig(
                    id="healthcheck_sdk",
                    category="healthcheck",
                    messages=[{"role": "user", "content": "Say OK"}],
                ),
                TestProfile(
                    name="healthcheck",
                    repetitions_per_prompt=1,
                    concurrency_levels=[1],
                    max_tokens=16,
                    temperature=0,
                    top_p=1,
                    timeout_sec=30,
                    stream=False,
                    store_response_text=True,
                ),
                str(uuid4()),
                run_id="",
                concurrency_level=1,
                repetition_index=0,
            )
        except Exception as exc:
            return HealthcheckResult(
                target_id=target.id,
                target_name=target.name,
                mode=target.mode,
                base_url=target.base_url,
                model=target.model,
                api_key_env=target.api_key_env,
                api_key_env_exists=bool(target.api_key_value()),
                setup_required=target.setup_required,
                service_reachable=False,
                models_works=None,
                chat_works=False,
                streaming_works=None,
                status_color="red",
                details=str(exc),
                setup_doc_section=target.setup_doc_section,
                setup_notes=target.notes,
            )
        return HealthcheckResult(
            target_id=target.id,
            target_name=target.name,
            mode=target.mode,
            base_url=target.base_url,
            model=target.model,
            api_key_env=target.api_key_env,
            api_key_env_exists=bool(target.api_key_value()),
            setup_required=target.setup_required,
            service_reachable=True,
            models_works=None,
            chat_works=True,
            streaming_works=None,
            status_color="green",
            details="LiteLLM SDK import smoke test passed.",
            setup_doc_section=target.setup_doc_section,
            setup_notes=target.notes,
        )

    async def _call_litellm(
        self,
        target: TargetConfig,
        prompt: PromptConfig,
        profile: TestProfile,
        client_request_id: str,
        *,
        run_id: str,
        concurrency_level: int,
        repetition_index: int,
    ) -> tuple[RequestResult, list[StreamEventModel]]:
        litellm = self._import_litellm()
        start = time.perf_counter()
        now = utc_now()
        result = RequestResult(
            run_id=run_id,
            target_id=target.id,
            target_name=target.name,
            prompt_id=prompt.id,
            prompt_category=prompt.category,
            concurrency_level=concurrency_level,
            repetition_index=repetition_index,
            request_started_at=now,
            status="error",
            client_request_id=client_request_id,
            model=target.model,
            base_url=target.base_url or "",
            stream=profile.stream,
            temperature=profile.temperature,
            top_p=profile.top_p,
            max_tokens=profile.max_tokens,
            prompt_chars=prompt.prompt_chars(),
            extra_json=json_dumps({"target_mode": target.mode, "adapter": "litellm_sdk"}),
        )
        try:
            response = await litellm.acompletion(
                model=target.model,
                messages=prompt.expanded_messages(),
                api_base=target.base_url,
                api_key=target.api_key_value(),
                temperature=profile.temperature,
                top_p=profile.top_p,
                max_tokens=profile.max_tokens,
                stream=profile.stream,
                **target.extra_body,
            )
            output_chunks: list[str] = []
            content_times: list[float] = []
            if profile.stream:
                async for chunk in response:
                    elapsed_ms = (time.perf_counter() - start) * 1000
                    if result.first_chunk_ms is None:
                        result.first_chunk_ms = elapsed_ms
                    result.chunk_count += 1
                    delta = ""
                    choices = getattr(chunk, "choices", None) or chunk.get("choices", [])
                    if choices:
                        choice = choices[0]
                        choice_delta = getattr(choice, "delta", None) or choice.get("delta", {})
                        delta = getattr(choice_delta, "content", None) or choice_delta.get("content") or ""
                    if delta:
                        if result.first_content_chunk_ms is None:
                            result.first_content_chunk_ms = elapsed_ms
                        result.content_chunk_count += 1
                        result.time_to_last_token_ms = elapsed_ms
                        content_times.append(elapsed_ms)
                        output_chunks.append(delta)
            else:
                choices = getattr(response, "choices", None) or response.get("choices", [])
                if choices:
                    message = getattr(choices[0], "message", None) or choices[0].get("message", {})
                    content = getattr(message, "content", None) or message.get("content") or ""
                    output_chunks.append(content)

            output_text = "".join(output_chunks)
            result.request_finished_at = utc_now()
            result.total_latency_ms = (time.perf_counter() - start) * 1000
            result.ttft_ms = result.first_content_chunk_ms
            result.output_text = output_text if profile.store_response_text else None
            result.output_chars = len(output_text)
            result.approx_output_tokens = approx_token_count(output_text)
            if result.approx_output_tokens and result.total_latency_ms:
                result.tokens_per_second_approx = result.approx_output_tokens / (
                    result.total_latency_ms / 1000
                )
            inter_chunk_deltas = [
                content_times[index] - content_times[index - 1]
                for index in range(1, len(content_times))
            ]
            if inter_chunk_deltas:
                result.mean_inter_content_chunk_ms = sum(inter_chunk_deltas) / len(
                    inter_chunk_deltas
                )
                result.p50_inter_content_chunk_ms = safe_percentile(inter_chunk_deltas, 50)
                result.p95_inter_content_chunk_ms = safe_percentile(inter_chunk_deltas, 95)
            if output_text:
                result.status = "success"
            else:
                result.error_type = "empty_response"
                result.error_message = "LiteLLM SDK response did not include content."
        except Exception as exc:
            result.request_finished_at = utc_now()
            result.total_latency_ms = (time.perf_counter() - start) * 1000
            result.error_type = "sdk_error"
            result.error_message = str(exc)
        return result, []

    async def run_streaming_chat(
        self,
        target: TargetConfig,
        prompt: PromptConfig,
        profile: TestProfile,
        client_request_id: str,
        *,
        run_id: str = "",
        concurrency_level: int = 1,
        repetition_index: int = 0,
    ) -> tuple[RequestResult, list[StreamEventModel]]:
        return await self._call_litellm(
            target,
            prompt,
            profile.model_copy(update={"stream": True}),
            client_request_id,
            run_id=run_id,
            concurrency_level=concurrency_level,
            repetition_index=repetition_index,
        )

    async def run_non_streaming_chat(
        self,
        target: TargetConfig,
        prompt: PromptConfig,
        profile: TestProfile,
        client_request_id: str,
        *,
        run_id: str = "",
        concurrency_level: int = 1,
        repetition_index: int = 0,
    ) -> tuple[RequestResult, list[StreamEventModel]]:
        return await self._call_litellm(
            target,
            prompt,
            profile.model_copy(update={"stream": False}),
            client_request_id,
            run_id=run_id,
            concurrency_level=concurrency_level,
            repetition_index=repetition_index,
        )


class ManualOnlyAdapter:
    async def healthcheck(self, target: TargetConfig) -> HealthcheckResult:
        return HealthcheckResult(
            target_id=target.id,
            target_name=target.name,
            mode=target.mode,
            base_url=target.base_url,
            model=target.model,
            api_key_env=target.api_key_env,
            api_key_env_exists=bool(target.api_key_value()),
            setup_required=target.setup_required,
            service_reachable=None,
            models_works=None,
            chat_works=None,
            streaming_works=None,
            status_color="gray",
            details="Manual-only target. Convert it to an openai_http target before benchmarking.",
            setup_doc_section=target.setup_doc_section,
            setup_notes=target.notes,
        )

    async def run_streaming_chat(
        self,
        target: TargetConfig,
        prompt: PromptConfig,
        profile: TestProfile,
        client_request_id: str,
        *,
        run_id: str = "",
        concurrency_level: int = 1,
        repetition_index: int = 0,
    ) -> tuple[RequestResult, list[StreamEventModel]]:
        return (
            _manual_result(
                target,
                prompt,
                profile,
                client_request_id,
                run_id=run_id,
                concurrency_level=concurrency_level,
                repetition_index=repetition_index,
                error_type="manual_only",
                error_message="Manual-only target cannot be benchmarked automatically.",
            ),
            [],
        )

    async def run_non_streaming_chat(
        self,
        target: TargetConfig,
        prompt: PromptConfig,
        profile: TestProfile,
        client_request_id: str,
        *,
        run_id: str = "",
        concurrency_level: int = 1,
        repetition_index: int = 0,
    ) -> tuple[RequestResult, list[StreamEventModel]]:
        return await self.run_streaming_chat(
            target,
            prompt,
            profile,
            client_request_id,
            run_id=run_id,
            concurrency_level=concurrency_level,
            repetition_index=repetition_index,
        )


def get_adapter(target: TargetConfig) -> TargetAdapter:
    if target.mode in {"openai_http", "managed_gateway"}:
        return OpenAIHTTPAdapter()
    if target.mode == "python_sdk" and target.id == "litellm_sdk":
        return LiteLLMSDKAdapter()
    return ManualOnlyAdapter()
