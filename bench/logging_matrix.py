from __future__ import annotations

from pathlib import Path

import pandas as pd

from bench.db import load_logging_assessments, upsert_logging_assessment
from bench.schemas import LoggingAssessment, TargetConfig
from bench.wrapper_registry import KNOWN_WRAPPERS


LOGGING_FEATURES = [
    "request_id",
    "client_request_id_preserved",
    "prompt_logging",
    "response_logging",
    "content_redaction",
    "token_usage",
    "cost_tracking",
    "latency_logging",
    "ttft_logging",
    "stream_logging",
    "error_logging",
    "retry_fallback_trace",
    "provider_model_logging",
    "virtual_key_logging",
    "user_team_logging",
    "prometheus_export",
    "opentelemetry_export",
    "file_or_db_export",
    "dashboard_ui",
    "log_search",
    "log_retention_config",
]

LOGGING_STATUSES = ["yes", "no", "partial", "unknown", "not_applicable"]


def ensure_default_logging_assessments(
    targets: list[TargetConfig], db_path: str | Path | None = None
) -> None:
    existing = load_logging_assessments(db_path)
    existing_pairs = set()
    if not existing.empty:
        existing_pairs = set(zip(existing["target_id"], existing["feature_name"], strict=False))
    target_ids = [target.id for target in targets]
    for known_id in KNOWN_WRAPPERS:
        if known_id not in target_ids:
            target_ids.append(known_id)
    for target_id in target_ids:
        for feature in LOGGING_FEATURES:
            if (target_id, feature) not in existing_pairs:
                upsert_logging_assessment(
                    LoggingAssessment(target_id=target_id, feature_name=feature),
                    db_path,
                )


def logging_matrix(db_path: str | Path | None = None) -> pd.DataFrame:
    df = load_logging_assessments(db_path)
    if df.empty:
        return pd.DataFrame()
    latest = df.sort_values("updated_at").drop_duplicates(
        ["target_id", "feature_name"], keep="last"
    )
    return latest.pivot(index="feature_name", columns="target_id", values="status")
