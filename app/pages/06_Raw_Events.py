from __future__ import annotations

import json

import streamlit as st

from bench.db import list_runs, load_request_results, load_stream_events


st.set_page_config(page_title="Raw Events", layout="wide")
st.title("Raw Events")

runs = list_runs()
if runs.empty:
    st.info("No benchmark runs recorded yet.")
    st.stop()

run_ids = runs["id"].astype(str).tolist()
run_id = st.selectbox("Run", run_ids)
requests = load_request_results(run_id=run_id)
if requests.empty:
    st.info("No request rows for this run.")
    st.stop()

targets = sorted(requests["target_id"].dropna().unique().tolist())
selected_targets = st.multiselect("Targets", targets, default=targets)
filtered = requests[requests["target_id"].isin(selected_targets)]

st.subheader("Request rows")
st.dataframe(filtered, use_container_width=True, hide_index=True)

request_ids = filtered["id"].astype(str).tolist()
selected_request_id = st.selectbox("Request", request_ids)
row = filtered[filtered["id"] == selected_request_id].iloc[0].to_dict()

with st.expander("Response headers", expanded=False):
    st.code(row.get("response_headers_json") or "")
with st.expander("Error", expanded=False):
    st.write({"error_type": row.get("error_type"), "error_message": row.get("error_message")})
with st.expander("Extra", expanded=False):
    st.code(row.get("extra_json") or "")

events = load_stream_events(request_result_id=selected_request_id)
st.subheader("Stream event timeline")
if events.empty:
    st.info("No stream events stored for this request.")
else:
    st.dataframe(events, use_container_width=True, hide_index=True)
    jsonl = "\n".join(
        json.dumps(item, default=str, ensure_ascii=False)
        for item in events.to_dict(orient="records")
    )
    st.download_button(
        "Download raw JSONL",
        jsonl.encode("utf-8"),
        f"{selected_request_id}_raw_events.jsonl",
        "application/jsonl",
    )
