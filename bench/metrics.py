from __future__ import annotations

import numpy as np
import pandas as pd


GROUP_COLUMNS = [
    "run_id",
    "target_id",
    "prompt_category",
    "prompt_id",
    "concurrency_level",
]


def _percentile(series: pd.Series, percentile: float) -> float | None:
    values = series.dropna().astype(float)
    if values.empty:
        return None
    return float(np.percentile(values, percentile))


def _mean(series: pd.Series) -> float | None:
    values = series.dropna().astype(float)
    if values.empty:
        return None
    return float(values.mean())


def _std(series: pd.Series) -> float | None:
    values = series.dropna().astype(float)
    if len(values) < 2:
        return 0.0 if len(values) == 1 else None
    return float(values.std(ddof=1))


def compute_summary(
    request_results: pd.DataFrame, baseline_target_id: str = "direct_vllm"
) -> pd.DataFrame:
    if request_results.empty:
        return pd.DataFrame()

    rows: list[dict] = []
    for group_values, group in request_results.groupby(GROUP_COLUMNS, dropna=False):
        group_key = dict(zip(GROUP_COLUMNS, group_values, strict=True))
        success = group[group["status"] == "success"]
        request_count = int(len(group))
        success_count = int(len(success))
        error_count = int((group["status"] == "error").sum())
        timeout_count = int((group["status"] == "timeout").sum())

        row = {
            **group_key,
            "request_count": request_count,
            "success_count": success_count,
            "error_count": error_count,
            "timeout_count": timeout_count,
            "success_rate": success_count / request_count if request_count else None,
            "error_rate": (error_count + timeout_count) / request_count if request_count else None,
            "ttft_p50_ms": _percentile(success["ttft_ms"], 50),
            "ttft_p90_ms": _percentile(success["ttft_ms"], 90),
            "ttft_p95_ms": _percentile(success["ttft_ms"], 95),
            "ttft_p99_ms": _percentile(success["ttft_ms"], 99),
            "ttft_mean_ms": _mean(success["ttft_ms"]),
            "ttft_std_ms": _std(success["ttft_ms"]),
            "total_latency_p50_ms": _percentile(success["total_latency_ms"], 50),
            "total_latency_p90_ms": _percentile(success["total_latency_ms"], 90),
            "total_latency_p95_ms": _percentile(success["total_latency_ms"], 95),
            "total_latency_p99_ms": _percentile(success["total_latency_ms"], 99),
            "total_latency_mean_ms": _mean(success["total_latency_ms"]),
            "total_latency_std_ms": _std(success["total_latency_ms"]),
            "tokens_per_second_p50": _percentile(
                success["tokens_per_second_approx"], 50
            ),
            "tokens_per_second_mean": _mean(success["tokens_per_second_approx"]),
            "output_chars_mean": _mean(success["output_chars"]),
            "chunk_count_mean": _mean(success["chunk_count"]),
            "content_chunk_count_mean": _mean(success["content_chunk_count"]),
        }
        rows.append(row)

    summary = pd.DataFrame(rows)
    if summary.empty:
        return summary

    baseline_columns = [
        "run_id",
        "prompt_category",
        "prompt_id",
        "concurrency_level",
        "ttft_p50_ms",
        "total_latency_p50_ms",
    ]
    baseline = summary[summary["target_id"] == baseline_target_id][baseline_columns].rename(
        columns={
            "ttft_p50_ms": "baseline_ttft_p50_ms",
            "total_latency_p50_ms": "baseline_total_latency_p50_ms",
        }
    )
    summary = summary.merge(
        baseline,
        how="left",
        on=["run_id", "prompt_category", "prompt_id", "concurrency_level"],
    )
    summary["ttft_overhead_p50_ms"] = (
        summary["ttft_p50_ms"] - summary["baseline_ttft_p50_ms"]
    )
    summary["latency_overhead_p50_ms"] = (
        summary["total_latency_p50_ms"]
        - summary["baseline_total_latency_p50_ms"]
    )
    summary["ttft_overhead_pct"] = np.where(
        summary["baseline_ttft_p50_ms"] > 0,
        summary["ttft_overhead_p50_ms"] / summary["baseline_ttft_p50_ms"] * 100,
        np.nan,
    )
    summary["latency_overhead_pct"] = np.where(
        summary["baseline_total_latency_p50_ms"] > 0,
        summary["latency_overhead_p50_ms"]
        / summary["baseline_total_latency_p50_ms"]
        * 100,
        np.nan,
    )
    return summary
