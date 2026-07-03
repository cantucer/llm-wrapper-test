from __future__ import annotations

import plotly.express as px
import streamlit as st

from bench.db import list_runs, load_request_results
from bench.export import export_run
from bench.metrics import compute_summary


st.set_page_config(page_title="Results", layout="wide")
st.title("Results")

runs = list_runs()
if runs.empty:
    st.info("No benchmark runs recorded yet.")
    st.stop()

run_ids = runs["id"].astype(str).tolist()
default_run = st.session_state.get("selected_run_id")
default_index = run_ids.index(default_run) if default_run in run_ids else 0
run_id = st.selectbox("Run", run_ids, index=default_index)
requests = load_request_results(run_id=run_id)

if requests.empty:
    st.info("No request results for this run.")
    st.stop()

targets = sorted(requests["target_id"].dropna().unique().tolist())
prompt_categories = sorted(requests["prompt_category"].dropna().unique().tolist())
prompt_ids = sorted(requests["prompt_id"].dropna().unique().tolist())
concurrency_levels = sorted(requests["concurrency_level"].dropna().unique().tolist())
statuses = sorted(requests["status"].dropna().unique().tolist())

with st.expander("Filters", expanded=False):
    selected_targets = st.multiselect("Targets", targets, default=targets)
    selected_categories = st.multiselect(
        "Prompt categories", prompt_categories, default=prompt_categories
    )
    selected_prompts = st.multiselect("Prompts", prompt_ids, default=prompt_ids)
    selected_concurrency = st.multiselect(
        "Concurrency", concurrency_levels, default=concurrency_levels
    )
    selected_statuses = st.multiselect("Status", statuses, default=statuses)

filtered = requests[
    requests["target_id"].isin(selected_targets)
    & requests["prompt_category"].isin(selected_categories)
    & requests["prompt_id"].isin(selected_prompts)
    & requests["concurrency_level"].isin(selected_concurrency)
    & requests["status"].isin(selected_statuses)
]
summary = compute_summary(filtered)

if summary.empty:
    st.warning("No successful rows match the current filters.")
else:
    best_ttft = summary.loc[summary["ttft_p50_ms"].idxmin()]
    best_latency = summary.loc[summary["total_latency_p50_ms"].idxmin()]
    lowest_error = summary.loc[summary["error_rate"].idxmin()]
    best_tps = summary.loc[summary["tokens_per_second_mean"].idxmax()]

    cols = st.columns(4)
    cols[0].metric("Best TTFT P50", f"{best_ttft['ttft_p50_ms']:.0f} ms", best_ttft["target_id"])
    cols[1].metric(
        "Best Latency P50",
        f"{best_latency['total_latency_p50_ms']:.0f} ms",
        best_latency["target_id"],
    )
    cols[2].metric(
        "Lowest Error Rate", f"{lowest_error['error_rate'] * 100:.1f}%", lowest_error["target_id"]
    )
    cols[3].metric(
        "Highest Tokens/sec",
        f"{best_tps['tokens_per_second_mean']:.1f}",
        best_tps["target_id"],
    )

    st.subheader("Summary")
    st.dataframe(summary, use_container_width=True, hide_index=True)

    chart_cols = st.columns(2)
    chart_cols[0].plotly_chart(
        px.bar(
            summary,
            x="target_id",
            y=["ttft_p50_ms", "ttft_p95_ms"],
            color="prompt_id",
            barmode="group",
            title="TTFT P50/P95 by target",
        ),
        use_container_width=True,
    )
    chart_cols[1].plotly_chart(
        px.bar(
            summary,
            x="target_id",
            y=["total_latency_p50_ms", "total_latency_p95_ms"],
            color="prompt_id",
            barmode="group",
            title="Total latency P50/P95 by target",
        ),
        use_container_width=True,
    )
    chart_cols = st.columns(2)
    chart_cols[0].plotly_chart(
        px.bar(summary, x="target_id", y="error_rate", color="prompt_id", title="Error rate"),
        use_container_width=True,
    )
    chart_cols[1].plotly_chart(
        px.bar(
            summary,
            x="target_id",
            y="tokens_per_second_mean",
            color="prompt_id",
            title="Tokens/sec by target",
        ),
        use_container_width=True,
    )
    chart_cols = st.columns(2)
    chart_cols[0].plotly_chart(
        px.bar(
            summary,
            x="target_id",
            y="ttft_overhead_p50_ms",
            color="prompt_id",
            title="TTFT overhead vs direct_vllm",
        ),
        use_container_width=True,
    )
    chart_cols[1].plotly_chart(
        px.bar(
            summary,
            x="target_id",
            y="latency_overhead_p50_ms",
            color="prompt_id",
            title="Latency overhead vs direct_vllm",
        ),
        use_container_width=True,
    )

st.subheader("Request rows")
st.dataframe(filtered, use_container_width=True, hide_index=True)

if st.button("Export run"):
    paths = export_run(run_id)
    st.write({name: str(path) for name, path in paths.items()})
