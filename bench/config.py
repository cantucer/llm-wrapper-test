from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

from bench.schemas import PromptConfig, TargetConfig, TestProfile


ENV_PATTERN = re.compile(r"\$\{([A-Za-z0-9_]+)\}")


def resolve_env_placeholders(value: Any) -> Any:
    if isinstance(value, str):
        return ENV_PATTERN.sub(
            lambda match: os.getenv(match.group(1), match.group(0)), value
        )
    if isinstance(value, list):
        return [resolve_env_placeholders(item) for item in value]
    if isinstance(value, dict):
        return {key: resolve_env_placeholders(item) for key, item in value.items()}
    return value


def load_yaml(path: str | Path) -> dict[str, Any]:
    load_dotenv()
    with Path(path).open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a YAML mapping")
    return resolve_env_placeholders(data)


def load_targets(path: str | Path) -> list[TargetConfig]:
    data = load_yaml(path)
    raw_targets = data.get("targets", [])
    if not isinstance(raw_targets, list):
        raise ValueError("targets must be a list")
    targets: list[TargetConfig] = []
    for raw_target in raw_targets:
        target = TargetConfig.model_validate(raw_target)
        if target.api_key_env and not target.api_key:
            target = target.model_copy(
                update={"resolved_api_key": os.getenv(target.api_key_env)}
            )
        targets.append(target)
    return targets


def load_enabled_targets(path: str | Path) -> list[TargetConfig]:
    return [target for target in load_targets(path) if target.enabled]


def load_prompts(path: str | Path) -> list[PromptConfig]:
    data = load_yaml(path)
    raw_prompts = data.get("prompts", [])
    if not isinstance(raw_prompts, list):
        raise ValueError("prompts must be a list")
    return [PromptConfig.model_validate(raw_prompt) for raw_prompt in raw_prompts]


def load_profiles(path: str | Path) -> dict[str, TestProfile]:
    data = load_yaml(path)
    raw_profiles = data.get("profiles", {})
    if not isinstance(raw_profiles, dict):
        raise ValueError("profiles must be a mapping")
    profiles: dict[str, TestProfile] = {}
    for name, raw_profile in raw_profiles.items():
        profile_data = dict(raw_profile)
        profile_data["name"] = name
        profiles[name] = TestProfile.model_validate(profile_data)
    return profiles
