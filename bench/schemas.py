from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from bench.utils import utc_now


TargetMode = Literal["openai_http", "python_sdk", "managed_gateway", "manual_only"]
TargetKind = Literal[
    "baseline",
    "service_gateway",
    "sdk_wrapper",
    "managed_gateway",
    "infra_gateway",
    "other",
]
RunStatus = Literal["created", "running", "completed", "failed", "cancelled"]
RequestStatus = Literal["success", "error", "timeout", "cancelled"]
CapabilityStatus = Literal[
    "pass",
    "fail",
    "partial",
    "warn",
    "skip",
    "manual",
    "unknown",
    "not_applicable",
]
LoggingStatus = Literal["yes", "no", "partial", "unknown", "not_applicable"]


class TargetConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    enabled: bool = True
    mode: TargetMode = "openai_http"
    kind: TargetKind = "service_gateway"
    base_url: str | None = None
    api_key_env: str | None = None
    api_key: str | None = Field(default=None, exclude=True)
    resolved_api_key: str | None = Field(default=None, exclude=True)
    model: str
    provider: str | None = None
    custom_host: str | None = None
    headers: dict[str, str] = Field(default_factory=dict)
    extra_body: dict[str, Any] = Field(default_factory=dict)
    healthcheck_enabled: bool = True
    models_endpoint_supported: bool = True
    chat_endpoint_path: str = "/chat/completions"
    setup_required: bool = True
    setup_doc_section: str | None = None
    notes: str | None = None

    @field_validator("id", "name", "model")
    @classmethod
    def non_empty_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be empty")
        return value

    @field_validator("base_url")
    @classmethod
    def optional_non_empty_text(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip()
        if not value:
            raise ValueError("must not be empty")
        return value

    @field_validator("kind", mode="before")
    @classmethod
    def migrate_old_kind_values(cls, value: str) -> str:
        mapping = {
            "direct": "baseline",
            "wrapper": "service_gateway",
            "managed": "managed_gateway",
        }
        return mapping.get(value, value)

    @field_validator("headers", mode="before")
    @classmethod
    def stringify_headers(cls, value: dict[str, Any] | None) -> dict[str, str]:
        if not value:
            return {}
        return {str(k): str(v) for k, v in value.items()}

    @field_validator("extra_body", mode="before")
    @classmethod
    def normalize_extra_body(cls, value: dict[str, Any] | None) -> dict[str, Any]:
        return dict(value or {})

    @field_validator("chat_endpoint_path")
    @classmethod
    def normalize_chat_endpoint_path(cls, value: str) -> str:
        value = value.strip() or "/chat/completions"
        return value if value.startswith("/") else f"/{value}"

    @model_validator(mode="after")
    def validate_mode_requirements(self) -> "TargetConfig":
        if self.mode in {"openai_http", "managed_gateway"} and not self.base_url:
            raise ValueError(f"{self.mode} targets require base_url")
        return self

    def api_key_value(self) -> str | None:
        return self.api_key or self.resolved_api_key


class PromptConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    category: str
    description: str | None = None
    messages: list[dict[str, str]]
    repeat_user_content: int | None = Field(default=None, ge=1)

    @field_validator("id", "category")
    @classmethod
    def non_empty_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be empty")
        return value

    @field_validator("messages")
    @classmethod
    def validate_messages(cls, value: list[dict[str, str]]) -> list[dict[str, str]]:
        if not value:
            raise ValueError("messages must contain at least one message")
        for message in value:
            if "role" not in message or "content" not in message:
                raise ValueError("each message must contain role and content")
            message["role"] = str(message["role"])
            message["content"] = str(message["content"])
        return value

    def expanded_messages(self) -> list[dict[str, str]]:
        messages = [dict(message) for message in self.messages]
        if not self.repeat_user_content:
            return messages
        for index in range(len(messages) - 1, -1, -1):
            if messages[index].get("role") == "user":
                content = messages[index].get("content", "")
                messages[index]["content"] = "\n\n".join(
                    content for _ in range(self.repeat_user_content)
                )
                return messages
        return messages

    def prompt_chars(self) -> int:
        return sum(len(message.get("content", "")) for message in self.expanded_messages())


class TestProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    repetitions_per_prompt: int = Field(ge=1)
    concurrency_levels: list[int]
    max_tokens: int = Field(ge=1)
    temperature: float = Field(ge=0)
    top_p: float = Field(gt=0, le=1)
    timeout_sec: int = Field(ge=1)
    stream: bool = True
    store_response_text: bool = True
    store_stream_events: bool = False

    @field_validator("concurrency_levels")
    @classmethod
    def valid_concurrency(cls, value: list[int]) -> list[int]:
        if not value:
            raise ValueError("concurrency_levels must not be empty")
        if any(level < 1 for level in value):
            raise ValueError("concurrency levels must be positive")
        return value


class BenchmarkRunConfig(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str
    profile_name: str
    profile: TestProfile
    targets: list[TargetConfig]
    prompts: list[PromptConfig]
    notes: str | None = None
    baseline_target_id: str = "direct_vllm"
    config_paths: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_non_empty_inputs(self) -> "BenchmarkRunConfig":
        if not self.targets:
            raise ValueError("at least one target is required")
        if not self.prompts:
            raise ValueError("at least one prompt is required")
        return self


class StreamEventModel(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    request_result_id: str
    event_index: int
    elapsed_ms: float
    event_type: str
    delta_text: str | None = None
    raw_event_json: str | None = None


class RequestResult(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    run_id: str
    target_id: str
    target_name: str
    prompt_id: str
    prompt_category: str
    concurrency_level: int
    repetition_index: int

    request_started_at: datetime
    request_finished_at: datetime | None = None

    status: RequestStatus
    error_type: str | None = None
    error_message: str | None = None

    http_status_code: int | None = None
    provider_request_id: str | None = None
    client_request_id: str

    model: str
    base_url: str

    stream: bool
    temperature: float
    top_p: float
    max_tokens: int

    ttft_ms: float | None = None
    total_latency_ms: float | None = None
    time_to_last_token_ms: float | None = None

    first_chunk_ms: float | None = None
    first_content_chunk_ms: float | None = None
    chunk_count: int = 0
    content_chunk_count: int = 0

    output_text: str | None = None
    output_chars: int = 0
    prompt_chars: int = 0

    prompt_tokens_reported: int | None = None
    completion_tokens_reported: int | None = None
    total_tokens_reported: int | None = None

    approx_output_tokens: int | None = None
    tokens_per_second_reported: float | None = None
    tokens_per_second_approx: float | None = None

    mean_inter_content_chunk_ms: float | None = None
    p50_inter_content_chunk_ms: float | None = None
    p95_inter_content_chunk_ms: float | None = None

    response_headers_json: str | None = None
    raw_usage_json: str | None = None
    extra_json: str | None = None


class CapabilityResult(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    run_id: str | None = None
    target_id: str
    capability_name: str
    status: CapabilityStatus
    details: str | None = None
    latency_ms: float | None = None
    raw_json: str | None = None
    created_at: datetime = Field(default_factory=utc_now)


class LoggingAssessment(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    target_id: str
    feature_name: str
    status: LoggingStatus = "unknown"
    evidence: str | None = None
    notes: str | None = None
    updated_at: datetime = Field(default_factory=utc_now)


class HealthcheckResult(BaseModel):
    target_id: str
    target_name: str
    mode: TargetMode
    base_url: str | None = None
    model: str
    api_key_env: str | None = None
    api_key_env_exists: bool = False
    setup_required: bool = True
    service_reachable: bool | None = None
    models_works: bool | None = None
    chat_works: bool | None = None
    streaming_works: bool | None = None
    status_color: Literal["green", "yellow", "red", "gray"] = "gray"
    details: str | None = None
    models_status_code: int | None = None
    chat_status_code: int | None = None
    streaming_status_code: int | None = None
    discovered_models: list[str] = Field(default_factory=list)
    curl_command: str | None = None
    setup_doc_section: str | None = None
    setup_notes: str | None = None
