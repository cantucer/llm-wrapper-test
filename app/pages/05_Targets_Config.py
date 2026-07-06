from __future__ import annotations

import asyncio
from pathlib import Path

import streamlit as st

from bench.capability_tests import check_target_health
from bench.config import load_targets
from bench.utils import generate_curl_test_command, mask_secret, mask_url
from bench.wrapper_registry import KNOWN_WRAPPERS


st.set_page_config(page_title="Targets Config", layout="wide")
st.title("Targets Config")


def default_targets_path() -> str:
    return (
        "configs/targets.yaml"
        if Path("configs/targets.yaml").exists()
        else "configs/targets.example.yaml"
    )


async def run_health_checks(selected_targets):
    return await asyncio.gather(
        *(check_target_health(target) for target in selected_targets)
    )


def health_flag_label(health: dict, key: str) -> str:
    if key not in health:
        return "not tested"
    value = health.get(key)
    if value is None:
        return "n/a"
    return "yes" if value else "no"


def setup_text(target_id: str, setup_doc_section: str | None) -> str:
    registry = KNOWN_WRAPPERS.get(target_id, {})
    lines = []
    if setup_doc_section:
        lines.append(f"USAGE.md section: {setup_doc_section}")
    if registry.get("setup"):
        lines.append(str(registry["setup"]))
    if registry.get("default_port"):
        lines.append(f"Default port: {registry['default_port']}")
    if registry:
        flags = [
            key.replace("supports_", "")
            for key, value in registry.items()
            if key.startswith("supports_") and value
        ]
        if flags:
            lines.append("Supported setup paths: " + ", ".join(flags))
    return "\n".join(lines) or "No registry setup metadata for this target."


targets_path = st.text_input("Targets config", default_targets_path())
if not Path(targets_path).exists():
    st.warning("Targets config does not exist.")
    st.stop()

try:
    targets = load_targets(targets_path)
except Exception as exc:
    st.error(str(exc))
    st.stop()

if "target_health_results" not in st.session_state:
    st.session_state["target_health_results"] = {}

health_results: dict[str, dict] = st.session_state["target_health_results"]

rows = []
for target in targets:
    health = health_results.get(target.id, {})
    rows.append(
        {
            "Target name": target.name,
            "Mode": target.mode,
            "Kind": target.kind,
            "Base URL": mask_url(target.base_url),
            "Model": target.model,
            "API key env var exists?": "yes" if target.api_key_value() else "no",
            "Setup required?": "yes" if target.setup_required else "no",
            "Service reachable?": health_flag_label(health, "service_reachable"),
            "/models works?": health_flag_label(health, "models_works"),
            "Small chat test works?": health_flag_label(health, "chat_works"),
            "Streaming chat test works?": health_flag_label(health, "streaming_works"),
            "Status": health.get("status_color", "gray"),
        }
    )
st.dataframe(rows, width="stretch", hide_index=True)

selected_id = st.selectbox("Selected target", [target.id for target in targets])
selected_target = next(target for target in targets if target.id == selected_id)

col_validate, col_all, col_curl, col_setup = st.columns(4)

if col_validate.button("Validate selected target"):
    with st.spinner(f"Validating {selected_target.name}..."):
        result = asyncio.run(run_health_checks([selected_target]))[0]
    health_results[selected_target.id] = result
    st.session_state["target_health_results"] = health_results
    st.rerun()

enabled_targets = [target for target in targets if target.enabled]
if col_all.button("Validate all enabled targets", disabled=not enabled_targets):
    with st.spinner("Validating enabled targets..."):
        results = asyncio.run(run_health_checks(enabled_targets))
    for result in results:
        health_results[result["target_id"]] = result
    st.session_state["target_health_results"] = health_results
    st.rerun()

with col_curl.popover("Copy curl test command"):
    if selected_target.mode in {"openai_http", "managed_gateway"} and selected_target.base_url:
        st.code(generate_curl_test_command(selected_target), language="bash")
    else:
        st.info("Curl generation applies to HTTP gateway targets with a base URL.")

with col_setup.popover("Show setup instructions"):
    st.text(setup_text(selected_target.id, selected_target.setup_doc_section))
    if selected_target.notes:
        st.write(selected_target.notes)
    if selected_target.api_key_env:
        st.write(
            {
                "api_key_env": selected_target.api_key_env,
                "api_key": mask_secret(selected_target.api_key_value()),
            }
        )

if selected_id in health_results:
    st.subheader("Latest validation result")
    st.json(health_results[selected_id])
