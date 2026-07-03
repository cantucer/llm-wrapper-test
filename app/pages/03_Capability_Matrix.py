from __future__ import annotations

import asyncio
from pathlib import Path

import streamlit as st

from bench.capability_tests import CAPABILITY_GROUPS, run_capability_tests
from bench.config import load_targets
from bench.db import load_capability_results


st.set_page_config(page_title="Capability Matrix", layout="wide")
st.title("Capability Matrix")


def default_targets_path() -> str:
    return (
        "configs/targets.yaml"
        if Path("configs/targets.yaml").exists()
        else "configs/targets.example.yaml"
    )


targets_path = st.text_input("Targets config", default_targets_path())
targets = []
if Path(targets_path).exists():
    try:
        targets = load_targets(targets_path)
    except Exception as exc:
        st.error(str(exc))
else:
    st.warning("Targets config does not exist.")

if targets:
    selected_ids = st.multiselect(
        "Targets", [target.id for target in targets], default=[target.id for target in targets if target.enabled]
    )
    selected_targets = [target for target in targets if target.id in selected_ids]
    selected_tests = []
    for group_name, tests in CAPABILITY_GROUPS.items():
        chosen = st.multiselect(group_name, tests, default=tests)
        selected_tests.extend(chosen)

    if st.button("Run capability tests", disabled=not selected_targets or not selected_tests):
        with st.spinner("Running capability tests..."):
            results = asyncio.run(run_capability_tests(selected_targets, selected_tests))
        st.success(f"Recorded {len(results)} capability results.")

df = load_capability_results()
if df.empty:
    st.info("No capability results recorded.")
else:
    latest = df.sort_values("created_at").drop_duplicates(
        ["target_id", "capability_name"], keep="last"
    )
    matrix = latest.pivot(index="capability_name", columns="target_id", values="status")
    st.dataframe(matrix, use_container_width=True)
    st.subheader("Details")
    st.dataframe(latest, use_container_width=True, hide_index=True)
    st.download_button(
        "Download capability matrix CSV",
        matrix.to_csv().encode("utf-8"),
        "capability_matrix.csv",
        "text/csv",
    )
