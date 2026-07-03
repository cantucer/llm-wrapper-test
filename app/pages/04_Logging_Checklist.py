from __future__ import annotations

from pathlib import Path

import streamlit as st

from bench.config import load_targets
from bench.db import load_logging_assessments, upsert_logging_assessment
from bench.logging_matrix import (
    LOGGING_STATUSES,
    ensure_default_logging_assessments,
    logging_matrix,
)
from bench.schemas import LoggingAssessment


st.set_page_config(page_title="Logging Checklist", layout="wide")
st.title("Logging Checklist")
st.info(
    "Some logging capabilities cannot be proven from the client side. Verify them in "
    "the wrapper dashboard, DB, logs, Prometheus endpoint, OpenTelemetry collector, or exported logs."
)


def default_targets_path() -> str:
    return (
        "configs/targets.yaml"
        if Path("configs/targets.yaml").exists()
        else "configs/targets.example.yaml"
    )


targets_path = st.text_input("Targets config", default_targets_path())
if not Path(targets_path).exists():
    st.warning("Targets config does not exist.")
    st.stop()

targets = load_targets(targets_path)
ensure_default_logging_assessments(targets)
df = load_logging_assessments()
target_ids = sorted(df["target_id"].dropna().unique().tolist())
target_id = st.selectbox("Target", target_ids)
target_df = df[df["target_id"] == target_id].sort_values("feature_name")

edited = st.data_editor(
    target_df[["feature_name", "status", "evidence", "notes"]],
    use_container_width=True,
    hide_index=True,
    column_config={
        "status": st.column_config.SelectboxColumn("status", options=LOGGING_STATUSES)
    },
    disabled=["feature_name"],
)

if st.button("Save checklist"):
    for row in edited.to_dict(orient="records"):
        upsert_logging_assessment(
            LoggingAssessment(
                target_id=target_id,
                feature_name=row["feature_name"],
                status=row["status"],
                evidence=row.get("evidence") or None,
                notes=row.get("notes") or None,
            )
        )
    st.success("Saved logging checklist.")

st.subheader("Comparison")
matrix = logging_matrix()
if matrix.empty:
    st.info("No logging assessments recorded.")
else:
    st.dataframe(matrix, use_container_width=True)
    st.download_button(
        "Download logging matrix CSV",
        matrix.to_csv().encode("utf-8"),
        "logging_matrix.csv",
        "text/csv",
    )
