from __future__ import annotations

import json
import shlex
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def json_loads(value: str | None, default: Any = None) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


def build_chat_completions_url(
    base_url: str | None, chat_endpoint_path: str = "/chat/completions"
) -> str:
    if not base_url:
        raise ValueError("base_url is required for chat completions")
    base = base_url.rstrip("/")
    endpoint = chat_endpoint_path if chat_endpoint_path.startswith("/") else f"/{chat_endpoint_path}"
    if base.endswith("/v1"):
        return f"{base}{endpoint}"
    return f"{base}/v1{endpoint}"


def build_models_url(base_url: str | None) -> str:
    if not base_url:
        raise ValueError("base_url is required for models endpoint")
    base = base_url.rstrip("/")
    if base.endswith("/v1"):
        return f"{base}/models"
    return f"{base}/v1/models"


def mask_secret(value: str | None, visible: int = 4) -> str:
    if not value:
        return ""
    if len(value) <= visible:
        return "*" * len(value)
    return f"{value[:visible]}...{'*' * 6}"


def mask_url(value: str | None) -> str:
    if not value:
        return ""
    if "://" not in value:
        return value
    scheme, rest = value.split("://", 1)
    host, _, path = rest.partition("/")
    if len(host) <= 8:
        masked_host = host
    else:
        masked_host = f"{host[:4]}...{host[-4:]}"
    return f"{scheme}://{masked_host}/{path}" if path else f"{scheme}://{masked_host}"


def redact_header_value(header_name: str, value: str) -> str:
    sensitive_names = ("authorization", "api-key", "apikey", "key", "token", "secret")
    if any(part in header_name.lower() for part in sensitive_names):
        return mask_secret(value)
    return value


def redact_headers(headers: dict[str, str]) -> dict[str, str]:
    return {name: redact_header_value(name, value) for name, value in headers.items()}


def shell_quote(value: str) -> str:
    return shlex.quote(value)


def generate_curl_test_command(target: Any) -> str:
    url = build_chat_completions_url(target.base_url, target.chat_endpoint_path)
    payload = {
        "model": target.model,
        "messages": [{"role": "user", "content": "Say OK"}],
        "stream": False,
    }
    api_key_reference = None
    if target.api_key_env:
        api_key_reference = f"${{{target.api_key_env}}}"
    elif target.api_key_value():
        api_key_reference = target.api_key_value()

    headers = {"Content-Type": "application/json", **target.headers}
    if api_key_reference:
        headers = {"Authorization": f"Bearer {api_key_reference}", **headers}

    lines = [f'curl -X POST "{url}" \\']
    for header_name, header_value in headers.items():
        lines.append(f'  -H "{header_name}: {header_value}" \\')
    body = json.dumps(payload, indent=2)
    lines.append(f"  -d {shell_quote(body)}")
    return "\n".join(lines)


def ensure_parent_dir(path: str | Path) -> Path:
    resolved = Path(path)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    return resolved


def safe_percentile(values: list[float], percentile: float) -> float | None:
    clean = sorted(v for v in values if v is not None)
    if not clean:
        return None
    if len(clean) == 1:
        return float(clean[0])
    rank = (len(clean) - 1) * (percentile / 100)
    lower = int(rank)
    upper = min(lower + 1, len(clean) - 1)
    weight = rank - lower
    return float(clean[lower] * (1 - weight) + clean[upper] * weight)


def approx_token_count(text: str | None) -> int | None:
    if not text:
        return 0
    return max(1, round(len(text) / 4))
