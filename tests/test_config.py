from __future__ import annotations

from bench.config import (
    load_profiles,
    load_prompts,
    load_targets,
    resolve_env_placeholders,
)


def test_resolve_env_placeholders_keeps_missing_values_visible(monkeypatch):
    monkeypatch.setenv("BASE_URL", "http://localhost:8000/v1")

    data = {
        "url": "${BASE_URL}",
        "missing": "${MISSING_VALUE}",
        "nested": ["x-${BASE_URL}"],
    }

    assert resolve_env_placeholders(data) == {
        "url": "http://localhost:8000/v1",
        "missing": "${MISSING_VALUE}",
        "nested": ["x-http://localhost:8000/v1"],
    }


def test_load_targets_resolves_api_key_from_env(tmp_path, monkeypatch):
    monkeypatch.setenv("TARGET_BASE_URL", "http://localhost:8000/v1")
    monkeypatch.setenv("TARGET_API_KEY", "sk-test")
    path = tmp_path / "targets.yaml"
    path.write_text(
        """
targets:
  - id: direct_vllm
    name: Direct
    kind: baseline
    mode: openai_http
    base_url: "${TARGET_BASE_URL}"
    api_key_env: TARGET_API_KEY
    model: qwen3-6
    headers:
      x-test: yes
""",
        encoding="utf-8",
    )

    targets = load_targets(path)

    assert len(targets) == 1
    assert targets[0].base_url == "http://localhost:8000/v1"
    assert targets[0].api_key_value() == "sk-test"
    assert targets[0].headers == {"x-test": "True"}
    assert targets[0].mode == "openai_http"
    assert targets[0].kind == "baseline"


def test_load_prompts_supports_repeat_user_content(tmp_path):
    path = tmp_path / "prompts.yaml"
    path.write_text(
        """
prompts:
  - id: long
    category: long
    repeat_user_content: 3
    messages:
      - role: system
        content: summarize
      - role: user
        content: chunk
""",
        encoding="utf-8",
    )

    prompt = load_prompts(path)[0]

    assert prompt.expanded_messages()[-1]["content"] == "chunk\n\nchunk\n\nchunk"


def test_load_profiles_uses_mapping_key_as_name(tmp_path):
    path = tmp_path / "profiles.yaml"
    path.write_text(
        """
profiles:
  quick:
    repetitions_per_prompt: 2
    concurrency_levels: [1, 2]
    max_tokens: 32
    temperature: 0
    top_p: 1
    timeout_sec: 30
""",
        encoding="utf-8",
    )

    profiles = load_profiles(path)

    assert profiles["quick"].name == "quick"
    assert profiles["quick"].concurrency_levels == [1, 2]
