from __future__ import annotations

from pathlib import Path

import streamlit as st

from bench.db import init_db, list_runs


def default_config_path(name: str) -> str:
    real_path = f"configs/{name}.yaml"
    example_path = f"configs/{name}.example.yaml"
    return real_path if Path(real_path).exists() else example_path


st.set_page_config(page_title="LLM Wrapper Benchmark", layout="wide")
init_db()

st.title("LLM Wrapper Benchmark")
st.caption("Compare OpenAI-compatible wrapper overhead against a direct vLLM baseline.")

st.write(
    "Use the pages in the sidebar to validate targets, run benchmarks, inspect results, "
    "record logging evidence, and export reports."
)

st.subheader("Configuration")
st.code(
    f"targets: {default_config_path('targets')}\n"
    f"prompts: {default_config_path('prompts')}\n"
    f"profiles: {default_config_path('test_profiles')}\n"
    "database: data/app.db"
)

st.subheader("Latest Runs")
runs = list_runs()
if runs.empty:
    st.info("No benchmark runs yet. Initialize configuration and start from Run Benchmark.")
else:
    st.dataframe(
        runs[["id", "name", "profile_name", "status", "created_at", "started_at", "finished_at"]],
        width="stretch",
        hide_index=True,
    )
    latest_id = str(runs.iloc[0]["id"])
    if st.button("Open latest results"):
        st.session_state["selected_run_id"] = latest_id
        st.switch_page("pages/02_Results.py")
