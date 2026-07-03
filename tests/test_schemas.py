from __future__ import annotations

import pytest
from pydantic import ValidationError

from bench.schemas import PromptConfig, TargetConfig, TestProfile as ProfileSchema
from bench.utils import generate_curl_test_command


def test_target_config_rejects_empty_http_url():
    with pytest.raises(ValidationError):
        TargetConfig(id="x", name="X", mode="openai_http", base_url="", model="m")


def test_target_config_allows_manual_only_without_url():
    target = TargetConfig(id="manual", name="Manual", mode="manual_only", model="m")

    assert target.base_url is None
    assert target.kind == "service_gateway"


def test_target_config_migrates_old_kind_values():
    target = TargetConfig(
        id="x",
        name="X",
        base_url="http://localhost:8000/v1",
        model="m",
        kind="direct",
    )

    assert target.kind == "baseline"


def test_target_config_stringifies_headers():
    target = TargetConfig(
        id="x",
        name="X",
        base_url="http://localhost:8000/v1",
        model="m",
        headers={"x-number": 5},
    )

    assert target.headers == {"x-number": "5"}


def test_generate_curl_uses_env_reference_for_api_key():
    target = TargetConfig(
        id="x",
        name="X",
        base_url="http://localhost:8000/v1",
        api_key_env="TARGET_API_KEY",
        model="m",
        headers={"x-extra": "value"},
    )

    command = generate_curl_test_command(target)

    assert 'curl -X POST "http://localhost:8000/v1/chat/completions"' in command
    assert "Authorization: Bearer ${TARGET_API_KEY}" in command
    assert "x-extra: value" in command


def test_prompt_requires_role_and_content():
    with pytest.raises(ValidationError):
        PromptConfig(id="p", category="short", messages=[{"role": "user"}])


def test_profile_requires_positive_concurrency():
    with pytest.raises(ValidationError):
        ProfileSchema(
            name="bad",
            repetitions_per_prompt=1,
            concurrency_levels=[0],
            max_tokens=16,
            temperature=0,
            top_p=1,
            timeout_sec=10,
        )
