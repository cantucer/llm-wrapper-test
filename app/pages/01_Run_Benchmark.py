from __future__ import annotations

import asyncio
from pathlib import Path

import streamlit as st

from bench.config import load_prompts, load_targets, load_profiles
from bench.export import export_run
from bench.runner import estimate_total_requests, run_benchmark
from bench.schemas import BenchmarkRunConfig
from bench.utils import mask_url


st.set_page_config(page_title="Run Benchmark", layout="wide")
st.title("Run Benchmark")


def default_config_path(name: str) -> str:
    real_path = f"configs/{name}.yaml"
    example_path = f"configs/{name}.example.yaml"
    return real_path if Path(real_path).exists() else example_path


targets_path = st.text_input("Targets config", default_config_path("targets"))
prompts_path = st.text_input("Prompts config", default_config_path("prompts"))
profiles_path = st.text_input("Profiles config", default_config_path("test_profiles"))

if not Path(targets_path).exists():
    st.warning("Targets config does not exist. Copy configs/targets.example.yaml first.")
if not Path(prompts_path).exists():
    st.warning("Prompts config does not exist. Copy configs/prompts.example.yaml first.")
if not Path(profiles_path).exists():
    st.warning("Profiles config does not exist. Copy configs/test_profiles.example.yaml first.")

targets = []
prompts = []
profiles = {}
config_error = None

if st.button("Validate configs") or (
    Path(targets_path).exists() and Path(prompts_path).exists() and Path(profiles_path).exists()
):
    try:
        targets = load_targets(targets_path)
        prompts = load_prompts(prompts_path)
        profiles = load_profiles(profiles_path)
        st.success(
            f"Loaded {len(targets)} targets, {len(prompts)} prompts, and {len(profiles)} profiles."
        )
    except Exception as exc:
        config_error = exc
        st.error(str(exc))

if targets and prompts and profiles and not config_error:
    st.subheader("Select targets")
    selected_targets = []
    for target in targets:
        col_enabled, col_name, col_mode, col_url, col_model, col_key = st.columns(
            [1, 3, 2, 4, 2, 2]
        )
        enabled = col_enabled.checkbox(
            "Use", value=target.enabled, key=f"target_{target.id}"
        )
        col_name.write(f"**{target.name}**  \n`{target.id}`")
        col_mode.write(f"{target.mode}  \n{target.kind}")
        col_url.write(mask_url(target.base_url))
        col_model.write(target.model)
        col_key.write("key set" if target.api_key_value() else "no key")
        if enabled:
            selected_targets.append(target)

    st.warning(
        "LiteLLM, Bifrost, Portkey, Helicone, LLM Gateway, and similar wrappers "
        "must already be running as services. This webapp validates them but does not start them."
    )
    st.info("Do not run a benchmark until all selected openai_http targets pass healthcheck.")
    health_results = st.session_state.get("target_health_results", {})
    if selected_targets:
        status_rows = []
        for target in selected_targets:
            health = health_results.get(target.id, {})
            color = health.get("status_color", "gray")
            if target.mode in {"openai_http", "managed_gateway"} and color != "green":
                if color == "gray":
                    message = "not tested"
                elif color == "yellow":
                    message = "reachable but chat/streaming did not fully pass"
                else:
                    message = "not reachable"
            else:
                message = "validated" if color == "green" else "not required"
            status_rows.append(
                {
                    "target": target.id,
                    "mode": target.mode,
                    "status": color,
                    "health": message,
                    "setup_required": target.setup_required,
                }
            )
        st.dataframe(status_rows, use_container_width=True, hide_index=True)

    st.subheader("Select prompts")
    selected_prompts = []
    for prompt in prompts:
        label = f"{prompt.id} ({prompt.category}, {prompt.prompt_chars()} chars)"
        if st.checkbox(label, value=True, key=f"prompt_{prompt.id}"):
            selected_prompts.append(prompt)

    st.subheader("Profile")
    profile_name = st.selectbox("Profile", list(profiles.keys()), index=0)
    base_profile = profiles[profile_name]

    with st.expander("Advanced overrides", expanded=False):
        repetitions = st.number_input(
            "Repetitions per prompt",
            min_value=1,
            value=base_profile.repetitions_per_prompt,
        )
        concurrency_text = st.text_input(
            "Concurrency levels",
            ",".join(str(item) for item in base_profile.concurrency_levels),
        )
        max_tokens = st.number_input("Max tokens", min_value=1, value=base_profile.max_tokens)
        temperature = st.number_input(
            "Temperature", min_value=0.0, value=float(base_profile.temperature)
        )
        top_p = st.number_input(
            "Top p", min_value=0.01, max_value=1.0, value=float(base_profile.top_p)
        )
        timeout_sec = st.number_input(
            "Timeout seconds", min_value=1, value=base_profile.timeout_sec
        )
        stream = st.checkbox("Streaming", value=base_profile.stream)
        store_response_text = st.checkbox(
            "Store response text", value=base_profile.store_response_text
        )
        store_stream_events = st.checkbox(
            "Store detailed stream events", value=base_profile.store_stream_events
        )

    try:
        concurrency_levels = [
            int(item.strip()) for item in concurrency_text.split(",") if item.strip()
        ]
        profile = base_profile.model_copy(
            update={
                "repetitions_per_prompt": int(repetitions),
                "concurrency_levels": concurrency_levels,
                "max_tokens": int(max_tokens),
                "temperature": float(temperature),
                "top_p": float(top_p),
                "timeout_sec": int(timeout_sec),
                "stream": stream,
                "store_response_text": store_response_text,
                "store_stream_events": store_stream_events,
            }
        )
    except Exception as exc:
        st.error(f"Invalid profile overrides: {exc}")
        st.stop()

    if store_response_text or store_stream_events:
        st.warning("Prompt/response-derived content can be stored in SQLite and exports.")

    run_name = st.text_input("Run name", f"{profile_name}-benchmark")
    notes = st.text_area("Notes", "")
    run_config = BenchmarkRunConfig(
        name=run_name,
        profile_name=profile_name,
        profile=profile,
        targets=selected_targets,
        prompts=selected_prompts,
        notes=notes or None,
        config_paths={
            "targets": targets_path,
            "prompts": prompts_path,
            "profiles": profiles_path,
        },
    )
    st.metric("Planned requests", estimate_total_requests(run_config))

    if st.button("Start benchmark", type="primary", disabled=not selected_targets or not selected_prompts):
        progress_bar = st.progress(0)
        status_box = st.empty()
        live_table = st.empty()
        rows = []

        def progress(event):
            total = event.get("total_requests") or 1
            completed = event.get("completed_requests") or 0
            progress_bar.progress(min(1.0, completed / total))
            status_box.write(
                f"{event.get('type')}: {completed}/{total} complete, "
                f"errors={event.get('error_count', 0)}"
            )
            if event.get("type") == "request_completed":
                rows.append(
                    {
                        "target": event.get("target_id"),
                        "prompt": event.get("prompt_id"),
                        "concurrency": event.get("concurrency_level"),
                        "status": event.get("status"),
                        "ttft_ms": event.get("latest_ttft_ms"),
                        "latency_ms": event.get("latest_latency_ms"),
                        "error_type": event.get("error_type"),
                    }
                )
                live_table.dataframe(rows[-100:], use_container_width=True)

        try:
            run_id = asyncio.run(run_benchmark(run_config, progress))
        except Exception as exc:
            st.error(f"Benchmark failed: {exc}")
        else:
            st.session_state["selected_run_id"] = run_id
            st.success(f"Benchmark completed: {run_id}")
            if st.button("Export this run"):
                paths = export_run(run_id)
                st.write({name: str(path) for name, path in paths.items()})
            if st.button("Open results"):
                st.switch_page("pages/02_Results.py")
