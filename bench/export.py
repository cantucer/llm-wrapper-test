from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from bench.db import (
    latest_run_id,
    load_capability_results,
    load_logging_assessments,
    load_request_results,
    load_stream_events,
    list_runs,
)
from bench.metrics import compute_summary
from bench.utils import ensure_parent_dir, json_loads


def _latest_per_capability(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    return df.sort_values("created_at").drop_duplicates(
        ["target_id", "capability_name"], keep="last"
    )


def _latest_logging(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    return df.sort_values("updated_at").drop_duplicates(
        ["target_id", "feature_name"], keep="last"
    )


def _markdown_table(df: pd.DataFrame) -> str:
    if df.empty:
        return ""
    table = (
        df.reset_index()
        if df.index.name or not isinstance(df.index, pd.RangeIndex)
        else df
    )
    table = table.fillna("")
    columns = [str(column) for column in table.columns]

    def cell(value) -> str:
        return str(value).replace("|", "\\|").replace("\n", " ")

    lines = [
        "| " + " | ".join(cell(column) for column in columns) + " |",
        "| " + " | ".join("---" for _ in columns) + " |",
    ]
    for row in table.itertuples(index=False, name=None):
        lines.append("| " + " | ".join(cell(value) for value in row) + " |")
    return "\n".join(lines)


def build_markdown_report(
    run_id: str,
    requests: pd.DataFrame,
    summary: pd.DataFrame,
    capabilities: pd.DataFrame,
    logging: pd.DataFrame,
    runs: pd.DataFrame,
) -> str:
    run_row = runs[runs["id"] == run_id]
    run_name = run_id
    config = {}
    if not run_row.empty:
        run_name = str(run_row.iloc[0]["name"])
        config = json_loads(str(run_row.iloc[0]["config_json"]), {})

    lines = [
        "# LLM Wrapper Benchmark Report",
        "",
        "## Run config",
        "",
        f"- Run ID: `{run_id}`",
        f"- Name: {run_name}",
        f"- Profile: {config.get('profile_name', '')}",
        f"- Requests: {len(requests)}",
        "",
        "## Targets",
        "",
    ]
    for target in config.get("targets", []):
        lines.append(
            f"- `{target.get('id')}`: {target.get('name')} ({target.get('kind')})"
        )
    lines.extend(["", "## Prompt set", ""])
    for prompt in config.get("prompts", []):
        lines.append(f"- `{prompt.get('id')}`: {prompt.get('category')}")

    lines.extend(["", "## Latency summary", ""])
    if summary.empty:
        lines.append("No successful latency summary is available.")
    else:
        lines.append(
            _markdown_table(
                summary[
                    [
                        "target_id",
                        "prompt_id",
                        "concurrency_level",
                        "success_rate",
                        "ttft_p50_ms",
                        "ttft_p95_ms",
                        "total_latency_p50_ms",
                        "total_latency_p95_ms",
                        "tokens_per_second_mean",
                    ]
                ]
            )
        )

    lines.extend(["", "## Wrapper overhead vs direct vLLM", ""])
    if summary.empty:
        lines.append("No overhead data is available.")
    else:
        lines.append(
            _markdown_table(
                summary[
                    [
                        "target_id",
                        "prompt_id",
                        "concurrency_level",
                        "ttft_overhead_p50_ms",
                        "ttft_overhead_pct",
                        "latency_overhead_p50_ms",
                        "latency_overhead_pct",
                    ]
                ]
            )
        )

    lines.extend(["", "## Concurrency behavior", ""])
    if not summary.empty:
        concurrency = (
            summary[
                [
                    "target_id",
                    "concurrency_level",
                    "request_count",
                    "success_rate",
                    "error_rate",
                    "ttft_p50_ms",
                    "total_latency_p50_ms",
                ]
            ]
            .groupby(["target_id", "concurrency_level"], as_index=False)
            .mean(numeric_only=True)
        )
        lines.append(_markdown_table(concurrency))

    lines.extend(["", "## Errors", ""])
    if requests.empty or "status" not in requests:
        lines.append("No request rows.")
    else:
        errors = requests[requests["status"] != "success"]
        if errors.empty:
            lines.append("No request errors recorded.")
        else:
            lines.append(
                _markdown_table(
                    errors[
                        [
                            "target_id",
                            "prompt_id",
                            "status",
                            "error_type",
                            "error_message",
                        ]
                    ].head(50)
                )
            )

    lines.extend(["", "## Capability matrix", ""])
    latest_capabilities = _latest_per_capability(capabilities)
    if latest_capabilities.empty:
        lines.append("No capability results recorded.")
    else:
        lines.append(
            _markdown_table(
                latest_capabilities.pivot(
                    index="capability_name", columns="target_id", values="status"
                )
            )
        )

    lines.extend(["", "## Logging matrix", ""])
    latest_logging = _latest_logging(logging)
    if latest_logging.empty:
        lines.append("No logging assessments recorded.")
    else:
        lines.append(
            _markdown_table(
                latest_logging.pivot(
                    index="feature_name", columns="target_id", values="status"
                )
            )
        )

    lines.extend(
        [
            "",
            "## Notes and interpretation",
            "",
            "Compare wrapper percentiles against the direct vLLM baseline. Treat small differences cautiously and rerun benchmarks under stable upstream load before drawing conclusions.",
        ]
    )
    return "\n".join(lines) + "\n"


def export_run(
    run_id: str,
    output_dir: str | Path = "results",
    *,
    db_path: str | Path | None = None,
    baseline_target_id: str = "direct_vllm",
) -> dict[str, Path]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    requests = load_request_results(db_path, run_id)
    summary = compute_summary(requests, baseline_target_id=baseline_target_id)
    capabilities = load_capability_results(db_path, run_id)
    if capabilities.empty:
        capabilities = load_capability_results(db_path)
    logging = load_logging_assessments(db_path)
    runs = list_runs(db_path)
    events = load_stream_events(db_path)

    paths = {
        "request_results": output / f"{run_id}_request_results.csv",
        "summary": output / f"{run_id}_summary.csv",
        "capability_matrix": output / f"{run_id}_capability_matrix.csv",
        "logging_matrix": output / f"{run_id}_logging_matrix.csv",
        "report": output / f"{run_id}_report.md",
        "raw_events": output / f"{run_id}_raw_events.jsonl",
    }

    requests.to_csv(paths["request_results"], index=False)
    summary.to_csv(paths["summary"], index=False)
    _latest_per_capability(capabilities).to_csv(paths["capability_matrix"], index=False)
    _latest_logging(logging).to_csv(paths["logging_matrix"], index=False)
    paths["report"].write_text(
        build_markdown_report(run_id, requests, summary, capabilities, logging, runs),
        encoding="utf-8",
    )
    with ensure_parent_dir(paths["raw_events"]).open("w", encoding="utf-8") as handle:
        for row in events.to_dict(orient="records"):
            handle.write(json.dumps(row, default=str, ensure_ascii=False) + "\n")
    return paths


def export_latest(
    output_dir: str | Path = "results", *, db_path: str | Path | None = None
) -> dict[str, Path]:
    run_id = latest_run_id(db_path)
    if not run_id:
        raise ValueError("no benchmark runs found")
    return export_run(run_id, output_dir, db_path=db_path)
