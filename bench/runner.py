from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any
from uuid import uuid4

from bench.adapters import get_adapter
from bench.db import create_benchmark_run, insert_request_result, update_run_status
from bench.schemas import BenchmarkRunConfig, RequestResult
from bench.utils import json_dumps, utc_now


ProgressCallback = Callable[[dict[str, Any]], None | Awaitable[None]]


async def _emit_progress(
    progress_callback: ProgressCallback | None, event: dict[str, Any]
) -> None:
    if not progress_callback:
        return
    maybe_awaitable = progress_callback(event)
    if maybe_awaitable is not None:
        await maybe_awaitable


def estimate_total_requests(run_config: BenchmarkRunConfig) -> int:
    return (
        len(run_config.profile.concurrency_levels)
        * len(run_config.targets)
        * len(run_config.prompts)
        * run_config.profile.repetitions_per_prompt
    )


async def run_benchmark(
    run_config: BenchmarkRunConfig,
    progress_callback: ProgressCallback | None = None,
    db_path: str | None = None,
) -> str:
    run_id = create_benchmark_run(run_config, db_path)
    update_run_status(run_id, "running", db_path, started=True)
    total_requests = estimate_total_requests(run_config)
    completed_requests = 0
    error_count = 0
    write_lock = asyncio.Lock()

    await _emit_progress(
        progress_callback,
        {
            "type": "run_started",
            "run_id": run_id,
            "total_requests": total_requests,
            "completed_requests": completed_requests,
        },
    )

    try:
        for concurrency_level in run_config.profile.concurrency_levels:
            for target in run_config.targets:
                for prompt in run_config.prompts:
                    semaphore = asyncio.Semaphore(concurrency_level)

                    async def run_one(repetition_index: int) -> RequestResult:
                        nonlocal completed_requests, error_count
                        async with semaphore:
                            client_request_id = str(uuid4())
                            adapter = get_adapter(target)
                            if run_config.profile.stream:
                                result, events = await adapter.run_streaming_chat(
                                    target,
                                    prompt,
                                    run_config.profile,
                                    client_request_id,
                                    run_id=run_id,
                                    concurrency_level=concurrency_level,
                                    repetition_index=repetition_index,
                                )
                            else:
                                result, events = await adapter.run_non_streaming_chat(
                                    target,
                                    prompt,
                                    run_config.profile,
                                    client_request_id,
                                    run_id=run_id,
                                    concurrency_level=concurrency_level,
                                    repetition_index=repetition_index,
                                )
                            async with write_lock:
                                insert_request_result(result, events, db_path)
                            completed_requests += 1
                            if result.status != "success":
                                error_count += 1
                            await _emit_progress(
                                progress_callback,
                                {
                                    "type": "request_completed",
                                    "run_id": run_id,
                                    "total_requests": total_requests,
                                    "completed_requests": completed_requests,
                                    "error_count": error_count,
                                    "target_id": target.id,
                                    "target_name": target.name,
                                    "prompt_id": prompt.id,
                                    "concurrency_level": concurrency_level,
                                    "repetition_index": repetition_index,
                                    "status": result.status,
                                    "latest_ttft_ms": result.ttft_ms,
                                    "latest_latency_ms": result.total_latency_ms,
                                    "error_type": result.error_type,
                                },
                            )
                            return result

                    tasks = [
                        asyncio.create_task(run_one(repetition_index))
                        for repetition_index in range(
                            run_config.profile.repetitions_per_prompt
                        )
                    ]
                    gathered = await asyncio.gather(*tasks, return_exceptions=True)
                    for repetition_index, item in enumerate(gathered):
                        if isinstance(item, Exception):
                            error_count += 1
                            completed_requests += 1
                            fallback = RequestResult(
                                run_id=run_id,
                                target_id=target.id,
                                target_name=target.name,
                                prompt_id=prompt.id,
                                prompt_category=prompt.category,
                                concurrency_level=concurrency_level,
                                repetition_index=repetition_index,
                                request_started_at=utc_now(),
                                request_finished_at=utc_now(),
                                status="error",
                                error_type="unknown_error",
                                error_message=str(item),
                                client_request_id=str(uuid4()),
                                model=target.model,
                                base_url=target.base_url or "",
                                stream=run_config.profile.stream,
                                temperature=run_config.profile.temperature,
                                top_p=run_config.profile.top_p,
                                max_tokens=run_config.profile.max_tokens,
                                prompt_chars=prompt.prompt_chars(),
                                extra_json=json_dumps({"source": "runner_exception"}),
                            )
                            async with write_lock:
                                insert_request_result(fallback, [], db_path)
                            await _emit_progress(
                                progress_callback,
                                {
                                    "type": "request_completed",
                                    "run_id": run_id,
                                    "total_requests": total_requests,
                                    "completed_requests": completed_requests,
                                    "error_count": error_count,
                                    "target_id": target.id,
                                    "prompt_id": prompt.id,
                                    "concurrency_level": concurrency_level,
                                    "repetition_index": repetition_index,
                                    "status": "error",
                                    "error_type": "runner_exception",
                                },
                            )
        update_run_status(run_id, "completed", db_path, finished=True)
        await _emit_progress(
            progress_callback,
            {
                "type": "run_completed",
                "run_id": run_id,
                "total_requests": total_requests,
                "completed_requests": completed_requests,
                "error_count": error_count,
            },
        )
        return run_id
    except Exception:
        update_run_status(run_id, "failed", db_path, finished=True)
        raise
