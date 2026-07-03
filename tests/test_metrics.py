from __future__ import annotations

import pandas as pd

from bench.metrics import compute_summary


def test_compute_summary_counts_statuses_and_overhead():
    df = pd.DataFrame(
        [
            {
                "run_id": "run",
                "target_id": "direct_vllm",
                "prompt_category": "short",
                "prompt_id": "p1",
                "concurrency_level": 1,
                "status": "success",
                "ttft_ms": 100,
                "total_latency_ms": 1000,
                "tokens_per_second_approx": 10,
                "output_chars": 100,
                "chunk_count": 5,
                "content_chunk_count": 4,
            },
            {
                "run_id": "run",
                "target_id": "direct_vllm",
                "prompt_category": "short",
                "prompt_id": "p1",
                "concurrency_level": 1,
                "status": "timeout",
                "ttft_ms": None,
                "total_latency_ms": None,
                "tokens_per_second_approx": None,
                "output_chars": 0,
                "chunk_count": 0,
                "content_chunk_count": 0,
            },
            {
                "run_id": "run",
                "target_id": "litellm",
                "prompt_category": "short",
                "prompt_id": "p1",
                "concurrency_level": 1,
                "status": "success",
                "ttft_ms": 130,
                "total_latency_ms": 1120,
                "tokens_per_second_approx": 9,
                "output_chars": 90,
                "chunk_count": 6,
                "content_chunk_count": 5,
            },
        ]
    )

    summary = compute_summary(df)
    direct = summary[summary["target_id"] == "direct_vllm"].iloc[0]
    wrapper = summary[summary["target_id"] == "litellm"].iloc[0]

    assert direct["request_count"] == 2
    assert direct["success_count"] == 1
    assert direct["timeout_count"] == 1
    assert direct["success_rate"] == 0.5
    assert wrapper["ttft_overhead_p50_ms"] == 30
    assert wrapper["latency_overhead_p50_ms"] == 120
    assert wrapper["ttft_overhead_pct"] == 30
