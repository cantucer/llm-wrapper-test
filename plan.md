# Project: LLM Wrapper Benchmark Webapp

## 1. Purpose

Build a fully Python web application for benchmarking and comparing multiple LLM gateway/wrapper tools against the same upstream OpenAI-compatible Qwen 3.6 vLLM endpoint.

The goal is to compare wrappers such as:

* Direct vLLM baseline
* LiteLLM proxy
* Bifrost gateway
* Other OpenAI-compatible gateways/proxies later, such as Portkey, Helicone, Cloudflare AI Gateway, Kong AI Gateway, etc.

The app must compare wrappers from three angles:

1. **Efficiency / latency**

   * TTFT: time to first token
   * Total latency
   * Inter-token latency
   * Streaming chunk behavior
   * Tokens/sec
   * Error rate
   * Timeout rate
   * P50 / P90 / P95 / P99 latency
   * Concurrency behavior

2. **Logging / observability differences**

   * What each wrapper logs
   * Whether prompt/response content is logged
   * Whether logs include request ID, model, provider, latency, tokens, cost, errors, retry/fallback trail, virtual key/team/user metadata
   * Whether logs can be exported to Prometheus, OpenTelemetry, files, DB, callbacks, etc.
   * Whether redaction/privacy mode is supported
   * Whether logs can be correlated with client-side request IDs

3. **Capability comparison**

   * Basic chat completion
   * Streaming
   * System prompt preservation
   * Long prompts
   * OpenAI-compatible parameters
   * vLLM-specific `extra_body` passthrough
   * Model listing
   * Error passthrough
   * Timeout handling
   * Virtual-key support
   * Rate limiting
   * Load balancing
   * Fallback
   * Caching
   * Observability exports
   * Optional: tool calling, JSON mode, embeddings, rerank if supported by the upstream endpoint and wrapper

This project must not judge model quality, because the model is the same Qwen 3.6 vLLM model behind every wrapper. The benchmark should isolate wrapper/gateway overhead and behavior.

---

## 2. Core benchmarking principle

Every benchmark target must call the same upstream model behavior as much as possible.

For each test run, keep these constant:

* Same prompt set
* Same model alias or equivalent configured alias
* Same `max_tokens`
* Same `temperature`
* Same `top_p`
* Same `stream=True` for TTFT tests
* Same timeout
* Same concurrency level
* Same number of repetitions
* Same client machine/network path as much as possible

Only this changes:

```text
base_url + api_key + wrapper-specific headers/model alias
```

Example targets:

```yaml
direct_vllm:
  name: Direct vLLM
  base_url: "https://your-vllm-endpoint/v1"
  api_key: "dummy-or-real-key"
  model: "qwen3-6"

litellm:
  name: LiteLLM Proxy
  base_url: "http://localhost:4000/v1"
  api_key: "sk-litellm-test"
  model: "qwen3-6"

bifrost:
  name: Bifrost Gateway
  base_url: "http://localhost:8080/v1"
  api_key: "sk-bifrost-test"
  model: "qwen3-6"
```

---

## 3. Tech stack

Use only Python for the webapp and benchmark logic.

Required stack:

```text
Python 3.11+
Streamlit
httpx
openai
pydantic
pydantic-settings
pandas
numpy
plotly
sqlalchemy
aiosqlite
pyyaml
python-dotenv
tenacity
tiktoken optional
```

Use Streamlit for the UI because it is Python-native and fast to implement.

Use SQLite for persistence because Streamlit reruns the script often. Do not store benchmark state only in memory or only in `st.session_state`.

Use async HTTP benchmarking with `httpx.AsyncClient` for precise streaming control. The official OpenAI client can be used for simple capability tests, but TTFT measurement should preferably use raw streaming HTTP via `httpx` to avoid hiding timing details.

---

## 4. Project structure

Create this structure:

```text
llm-wrapper-bench/
  README.md
  pyproject.toml
  .env.example
  .gitignore

  configs/
    targets.example.yaml
    prompts.example.yaml
    test_profiles.example.yaml

  app/
    __init__.py
    main.py

    pages/
      __init__.py
      01_Run_Benchmark.py
      02_Results.py
      03_Capability_Matrix.py
      04_Logging_Checklist.py
      05_Targets_Config.py
      06_Raw_Events.py

  bench/
    __init__.py
    config.py
    schemas.py
    db.py
    http_client.py
    runner.py
    metrics.py
    capability_tests.py
    logging_matrix.py
    export.py
    utils.py

  scripts/
    init_db.py
    run_cli_benchmark.py
    export_latest.py

  data/
    app.db

  results/
    .gitkeep

  tests/
    test_metrics.py
    test_config.py
    test_schemas.py
```

---

## 5. Config files

### 5.1 `configs/targets.example.yaml`

```yaml
targets:
  - id: direct_vllm
    name: Direct vLLM
    enabled: true
    kind: direct
    base_url: "${DIRECT_VLLM_BASE_URL}"
    api_key_env: "DIRECT_VLLM_API_KEY"
    model: "qwen3-6"
    headers:
      x-benchmark-target: "direct_vllm"
    notes: "Direct baseline against OpenAI-compatible vLLM endpoint."

  - id: litellm
    name: LiteLLM Proxy
    enabled: true
    kind: wrapper
    base_url: "${LITELLM_BASE_URL}"
    api_key_env: "LITELLM_API_KEY"
    model: "qwen3-6"
    headers:
      x-benchmark-target: "litellm"
    notes: "LiteLLM proxy configured to route to same Qwen vLLM endpoint."

  - id: bifrost
    name: Bifrost Gateway
    enabled: true
    kind: wrapper
    base_url: "${BIFROST_BASE_URL}"
    api_key_env: "BIFROST_API_KEY"
    model: "qwen3-6"
    headers:
      x-benchmark-target: "bifrost"
    notes: "Bifrost gateway configured to route to same Qwen vLLM endpoint."
```

Support environment substitution for `${VAR_NAME}`.

### 5.2 `.env.example`

```bash
DIRECT_VLLM_BASE_URL=https://your-vllm-endpoint/v1
DIRECT_VLLM_API_KEY=dummy

LITELLM_BASE_URL=http://localhost:4000/v1
LITELLM_API_KEY=sk-litellm-test

BIFROST_BASE_URL=http://localhost:8080/v1
BIFROST_API_KEY=sk-bifrost-test

BENCH_DB_PATH=data/app.db
```

### 5.3 `configs/prompts.example.yaml`

Include multiple prompt types so wrappers are tested under different loads.

```yaml
prompts:
  - id: short_basic
    category: short
    description: "Short factual answer."
    messages:
      - role: system
        content: "You are a concise assistant."
      - role: user
        content: "Explain what DNS is in one sentence."

  - id: medium_reasoning
    category: medium
    description: "Medium reasoning prompt."
    messages:
      - role: system
        content: "You are a careful technical assistant."
      - role: user
        content: "Compare API gateways and LLM gateways. Give 5 practical differences."

  - id: long_context
    category: long
    description: "Long prompt to test prefill behavior."
    messages:
      - role: system
        content: "You are a technical summarizer."
      - role: user
        content: |
          Summarize the following artificial document into 5 bullets.
          Repeat this paragraph 50 times in the generated config or dynamically expand it in code:
          LLM gateways provide a unified interface, logging, rate limits, fallback, load balancing, and governance.
```

Implementation detail: allow dynamic prompt expansion with a `repeat` field instead of manually writing huge text.

### 5.4 `configs/test_profiles.example.yaml`

```yaml
profiles:
  quick:
    repetitions_per_prompt: 3
    concurrency_levels: [1]
    max_tokens: 128
    temperature: 0.0
    top_p: 1.0
    timeout_sec: 120
    stream: true

  standard:
    repetitions_per_prompt: 10
    concurrency_levels: [1, 2, 4, 8]
    max_tokens: 256
    temperature: 0.0
    top_p: 1.0
    timeout_sec: 180
    stream: true

  stress:
    repetitions_per_prompt: 25
    concurrency_levels: [1, 2, 4, 8, 16, 32]
    max_tokens: 256
    temperature: 0.0
    top_p: 1.0
    timeout_sec: 240
    stream: true
```

---

## 6. Data model

Use SQLite through SQLAlchemy.

### 6.1 Tables

#### `benchmark_runs`

One row per benchmark run.

Fields:

```text
id: string UUID primary key
created_at: datetime
name: string
profile_name: string
status: string enum: created/running/completed/failed/cancelled
started_at: datetime nullable
finished_at: datetime nullable
notes: text nullable
config_json: text
```

#### `request_results`

One row per individual LLM request.

Fields:

```text
id: string UUID primary key
run_id: foreign key benchmark_runs.id
target_id: string
target_name: string
prompt_id: string
prompt_category: string
concurrency_level: int
repetition_index: int

request_started_at: datetime
request_finished_at: datetime nullable

status: string enum: success/error/timeout/cancelled
error_type: string nullable
error_message: text nullable

http_status_code: int nullable
provider_request_id: string nullable
client_request_id: string

model: string
base_url: string

stream: bool
temperature: float
top_p: float
max_tokens: int

ttft_ms: float nullable
total_latency_ms: float nullable
time_to_last_token_ms: float nullable

first_chunk_ms: float nullable
first_content_chunk_ms: float nullable
chunk_count: int
content_chunk_count: int

output_text: text nullable
output_chars: int
prompt_chars: int

prompt_tokens_reported: int nullable
completion_tokens_reported: int nullable
total_tokens_reported: int nullable

approx_output_tokens: int nullable
tokens_per_second_reported: float nullable
tokens_per_second_approx: float nullable

response_headers_json: text nullable
raw_usage_json: text nullable
extra_json: text nullable
```

Important latency definitions:

```text
request_started_at = timestamp immediately before HTTP request starts
first_chunk_ms = first SSE chunk received, even if no content
first_content_chunk_ms = first streamed chunk with actual generated text
ttft_ms = first_content_chunk_ms
total_latency_ms = full response completed - request start
time_to_last_token_ms = last content token time - request start
```

#### `stream_events`

Optional but useful for debugging streaming behavior.

Fields:

```text
id: string UUID primary key
request_result_id: foreign key request_results.id
event_index: int
elapsed_ms: float
event_type: string
delta_text: text nullable
raw_event_json: text nullable
```

Only store this when “store detailed stream events” is enabled.

#### `capability_results`

One row per target per capability test.

Fields:

```text
id: string UUID primary key
run_id: foreign key benchmark_runs.id nullable
target_id: string
capability_name: string
status: string enum: pass/fail/skip/warn
details: text nullable
latency_ms: float nullable
raw_json: text nullable
created_at: datetime
```

#### `logging_assessments`

Manual/semi-automated logging matrix.

Fields:

```text
id: string UUID primary key
target_id: string
feature_name: string
status: string enum: yes/no/partial/unknown/not_applicable
evidence: text nullable
notes: text nullable
updated_at: datetime
```

Logging features to include:

```text
request_id
prompt_logging
response_logging
content_redaction
token_usage
cost_tracking
latency_logging
ttft_logging
stream_logging
error_logging
retry_fallback_trace
provider_model_logging
virtual_key_logging
user_team_logging
prometheus_export
opentelemetry_export
file_or_db_export
custom_callbacks_or_webhooks
dashboard_ui
log_search
log_retention_config
```

---

## 7. Python modules

### 7.1 `bench/schemas.py`

Create Pydantic models:

```text
TargetConfig
PromptConfig
TestProfile
BenchmarkRunConfig
RequestResult
CapabilityResult
LoggingAssessment
```

`TargetConfig` fields:

```python
id: str
name: str
enabled: bool = True
kind: Literal["direct", "wrapper", "managed", "other"]
base_url: str
api_key_env: str | None = None
api_key: str | None = None
model: str
headers: dict[str, str] = {}
notes: str | None = None
```

`PromptConfig` fields:

```python
id: str
category: str
description: str | None
messages: list[dict[str, str]]
repeat_user_content: int | None = None
```

`TestProfile` fields:

```python
name: str
repetitions_per_prompt: int
concurrency_levels: list[int]
max_tokens: int
temperature: float
top_p: float
timeout_sec: int
stream: bool = True
store_response_text: bool = True
store_stream_events: bool = False
```

### 7.2 `bench/config.py`

Responsibilities:

* Load YAML config files
* Substitute env vars like `${DIRECT_VLLM_BASE_URL}`
* Resolve API keys from env vars
* Validate using Pydantic
* Return enabled targets/prompts/profiles

Functions:

```python
load_targets(path: str) -> list[TargetConfig]
load_prompts(path: str) -> list[PromptConfig]
load_profiles(path: str) -> dict[str, TestProfile]
resolve_env_placeholders(value: Any) -> Any
```

### 7.3 `bench/http_client.py`

This is the most important module.

Use `httpx.AsyncClient`.

Implement:

```python
async def run_streaming_chat_completion(
    target: TargetConfig,
    prompt: PromptConfig,
    profile: TestProfile,
    client_request_id: str,
) -> RequestMeasurement:
    ...
```

Raw request endpoint:

```text
POST {target.base_url}/chat/completions
```

But be careful:

If `base_url` ends with `/v1`, endpoint should be:

```text
{base_url}/chat/completions
```

If it does not, normalize it.

Request JSON:

```json
{
  "model": "...",
  "messages": [...],
  "temperature": 0.0,
  "top_p": 1.0,
  "max_tokens": 256,
  "stream": true,
  "stream_options": {
    "include_usage": true
  }
}
```

Headers:

```text
Authorization: Bearer <api_key>
Content-Type: application/json
x-client-request-id: <uuid>
plus target.headers
```

Streaming parser:

* Parse Server-Sent Events lines.
* Ignore empty lines.
* For lines beginning with `data:`, strip `data:`.
* If payload is `[DONE]`, finish.
* JSON parse payload.
* Extract:

  * `choices[0].delta.content`
  * `usage` if present
  * `id` if present
  * model if present
* Record:

  * first raw SSE event time
  * first content delta time
  * every content chunk time
  * full output text

Handle errors:

* HTTP 4xx/5xx
* timeouts
* malformed SSE
* connection drop
* no first token
* empty output

Return a structured measurement object.

Also implement non-streaming:

```python
async def run_non_streaming_chat_completion(...)
```

But TTFT requires streaming, so main benchmark should use streaming.

### 7.4 `bench/runner.py`

Responsibilities:

* Create benchmark run record
* For each target
* For each concurrency level
* For each prompt
* For each repetition
* Run requests with bounded concurrency
* Persist each result immediately
* Never wait until the full benchmark ends to save results
* Allow partial results if the benchmark crashes

Core logic:

```python
async def run_benchmark(
    run_config: BenchmarkRunConfig,
    progress_callback: Callable | None = None,
) -> str:
    ...
```

Concurrency implementation:

```python
semaphore = asyncio.Semaphore(concurrency_level)
tasks = [...]
results = await asyncio.gather(*tasks, return_exceptions=True)
```

Important: concurrency means simultaneous requests for the same target/prompt/profile. Do not mix different targets inside the same concurrency batch unless explicitly desired, because that makes target comparison noisier.

Recommended ordering:

```text
for concurrency in concurrency_levels:
  for target in targets:
    for prompt in prompts:
      run N repetitions with this concurrency
```

This makes comparison easier.

### 7.5 `bench/metrics.py`

Compute summary metrics.

Input: DataFrame from `request_results`.

Output grouped by:

```text
run_id
target_id
prompt_category
prompt_id
concurrency_level
```

Metrics:

```text
request_count
success_count
error_count
timeout_count
success_rate
error_rate

ttft_p50_ms
ttft_p90_ms
ttft_p95_ms
ttft_p99_ms
ttft_mean_ms
ttft_std_ms

total_latency_p50_ms
total_latency_p90_ms
total_latency_p95_ms
total_latency_p99_ms
total_latency_mean_ms
total_latency_std_ms

tokens_per_second_p50
tokens_per_second_mean

output_chars_mean
chunk_count_mean
content_chunk_count_mean
```

Also compute wrapper overhead against baseline.

Assume baseline target id is configurable, default:

```text
direct_vllm
```

Overhead metrics:

```text
ttft_overhead_p50_ms = target.ttft_p50_ms - direct_vllm.ttft_p50_ms
latency_overhead_p50_ms = target.total_latency_p50_ms - direct_vllm.total_latency_p50_ms
ttft_overhead_pct = overhead / baseline * 100
latency_overhead_pct = overhead / baseline * 100
```

### 7.6 `bench/capability_tests.py`

Implement capability tests independent from latency benchmarks.

Tests:

1. `models_list`

   * GET `/models`
   * Pass if 200 and model list parseable.

2. `basic_chat`

   * Simple non-streaming chat completion.

3. `streaming_chat`

   * Streaming chat completion.
   * Pass if at least one content chunk arrives.

4. `system_prompt`

   * Ask model to answer in a constrained format from system prompt.
   * This is probabilistic; mark as warn/pass based on simple output check.

5. `long_prompt`

   * Generate long prompt.
   * Pass if request succeeds.

6. `bad_model_error`

   * Use fake model name.
   * Pass if wrapper returns clean 4xx/structured error.

7. `timeout_behavior`

   * Set tiny timeout.
   * Pass if client catches timeout cleanly.

8. `extra_body_passthrough`

   * Send vLLM-specific parameter through payload.
   * Example: include safe extra parameter if known and accepted by endpoint.
   * If wrapper rejects unknown params, mark fail/partial.
   * Make this configurable because exact vLLM parameters may differ.

9. `custom_header_passthrough`

   * Send `x-client-request-id`.
   * Cannot fully verify upstream received it unless upstream logs are available.
   * Mark as “client sent”; optional manual verification.

10. `stream_usage`

* Use `stream_options: {"include_usage": true}`.
* Check if final streamed usage object appears.
* Mark pass/fail/partial.

Optional tests:

```text
tool_calling
json_mode
embeddings
rerank
caching
rate_limit
fallback
load_balancing
```

For optional tests, the UI should allow enabling/disabling each test.

### 7.7 `bench/logging_matrix.py`

This is not fully automatable across wrappers. Implement a semi-automated checklist.

Create default feature rows for each target:

```python
LOGGING_FEATURES = [
    "request_id",
    "prompt_logging",
    "response_logging",
    "content_redaction",
    "token_usage",
    "cost_tracking",
    "latency_logging",
    "ttft_logging",
    "stream_logging",
    "error_logging",
    "retry_fallback_trace",
    "provider_model_logging",
    "virtual_key_logging",
    "user_team_logging",
    "prometheus_export",
    "opentelemetry_export",
    "file_or_db_export",
    "custom_callbacks_or_webhooks",
    "dashboard_ui",
    "log_search",
    "log_retention_config",
]
```

UI should allow user to mark each as:

```text
yes / no / partial / unknown / not_applicable
```

Also allow evidence text:

```text
"Seen in LiteLLM dashboard"
"Header x-litellm-call-id returned"
"Bifrost LogStore contains latency and token usage"
"Prometheus /metrics endpoint available"
```

### 7.8 `bench/export.py`

Export:

```text
results/<run_id>_request_results.csv
results/<run_id>_summary.csv
results/<run_id>_capability_matrix.csv
results/<run_id>_logging_matrix.csv
results/<run_id>_report.md
results/<run_id>_raw_events.jsonl
```

Markdown report should include:

```text
# LLM Wrapper Benchmark Report

## Run config
## Targets
## Prompt set
## Latency summary
## Wrapper overhead vs direct vLLM
## Concurrency behavior
## Errors
## Capability matrix
## Logging matrix
## Notes and interpretation
```

---

## 8. Streamlit UI

### 8.1 `app/main.py`

Main page:

* Project title
* Short explanation
* Current config paths
* Quick links to pages
* Latest runs table
* “Open latest results” button

Use Streamlit multipage layout.

### 8.2 Page: `01_Run_Benchmark.py`

Sections:

1. **Load configuration**

   * Targets config path
   * Prompts config path
   * Test profile config path
   * Button: Validate configs

2. **Select targets**

   * Checkbox per target
   * Show base URL masked
   * Show model
   * Show whether API key env var exists

3. **Select prompts**

   * Checkbox per prompt
   * Show category and prompt length

4. **Select profile**

   * Dropdown: quick / standard / stress
   * Advanced override fields:

     * repetitions
     * concurrency levels
     * max tokens
     * temperature
     * top_p
     * timeout
     * store response text
     * store detailed stream events

5. **Run benchmark**

   * Button: Start benchmark
   * Progress bar
   * Live status table:

     * target
     * prompt
     * concurrency
     * completed requests
     * errors
     * latest TTFT
     * latest latency

6. **After run**

   * Link/button to Results page
   * Export buttons

Implementation note:

Streamlit can be tricky with truly background jobs. For first version, run the benchmark synchronously after button click, but persist results after each request. That is acceptable. Later add a worker thread/process if needed.

### 8.3 Page: `02_Results.py`

Features:

* Select run dropdown
* Summary cards:

  * Best TTFT P50
  * Best total latency P50
  * Lowest error rate
  * Highest tokens/sec
* Data table grouped by target/concurrency
* Charts:

  * TTFT P50/P95 by target
  * Total latency P50/P95 by target
  * Error rate by target
  * Tokens/sec by target
  * TTFT overhead vs direct baseline
  * Latency overhead vs direct baseline
* Filters:

  * target
  * prompt category
  * prompt id
  * concurrency level
  * status

Use Plotly for charts.

### 8.4 Page: `03_Capability_Matrix.py`

Features:

* Select targets
* Select capability tests
* Button: Run capability tests
* Matrix table:

  * rows: capabilities
  * columns: targets
  * values: pass/fail/warn/skip
* Expandable details per result
* Export capability matrix CSV

### 8.5 Page: `04_Logging_Checklist.py`

Features:

* Select target
* Show checklist of logging features
* Editable status dropdown per feature
* Evidence text area
* Notes text area
* Save button
* Comparison table across targets
* Export logging matrix

This page should include a note:

```text
Some logging capabilities cannot be proven from the client side. Verify them in the wrapper dashboard, DB, logs, Prometheus endpoint, OpenTelemetry collector, or exported logs.
```

### 8.6 Page: `05_Targets_Config.py`

Features:

* Show current parsed targets
* Mask API keys
* Validate endpoint health:

  * GET `/models`
  * POST small chat completion
* Show results:

  * reachable/unreachable
  * status code
  * discovered models
  * error message

### 8.7 Page: `06_Raw_Events.py`

Features:

* Select run
* Select target
* Show raw request rows
* Expand response headers
* Expand errors
* Expand stream event timeline if stored
* Download raw JSONL

---

## 9. TTFT measurement details

TTFT must be measured only with streaming.

Definitions:

```text
start_time = immediately before sending HTTP request
first_raw_chunk_time = first SSE data received from server
first_content_chunk_time = first SSE chunk containing non-empty generated text
end_time = after final [DONE] or stream close
```

Use:

```text
TTFT = first_content_chunk_time - start_time
Total latency = end_time - start_time
```

Store both first raw chunk and first content chunk because some gateways may send initial empty chunks or metadata chunks.

For inter-token latency:

```text
For every content chunk timestamp:
  delta_i = timestamp_i - timestamp_{i-1}
```

Store aggregate:

```text
mean_inter_content_chunk_ms
p50_inter_content_chunk_ms
p95_inter_content_chunk_ms
```

Do not call this exact token latency unless tokenizer-level token IDs are available. Use the phrase “content chunk latency” unless actual token counts are available.

---

## 10. Capability philosophy

The capability matrix should distinguish:

```text
pass = verified automatically
fail = tested and failed
partial = works with caveat
warn = suspicious/probabilistic
skip = not tested
unknown = cannot verify from client side
not_applicable = upstream/wrapper does not support this class of feature
```

Example:

```text
Tool calling:
- not_applicable if Qwen/vLLM endpoint is not configured for tool calling
- pass if tool schema request produces valid tool call
- fail if wrapper rejects tool fields
```

---

## 11. Logging comparison philosophy

Do not assume logging is good because a wrapper claims observability.

For each wrapper, compare:

### Client-visible evidence

* Response headers
* Request IDs
* Error structure
* Usage fields
* Timing behavior
* Cache headers if any

### Gateway-visible evidence

The user manually checks wrapper dashboard/logs and records evidence.

Examples:

```text
LiteLLM:
- Does UI show request?
- Does it show spend/tokens?
- Does it show virtual key/team?
- Does it store prompt/response or only metadata?
- Is x-litellm-call-id visible?

Bifrost:
- Does LogStore show request?
- Does it show input/output?
- Does it show latency/tokens/cost?
- Does attempt trail show retry/fallback?
- Does /metrics expose gateway metrics?
```

The app should provide the matrix and evidence fields, not pretend to automatically inspect every external dashboard.

---

## 12. Failure tests

Implement explicit failure profiles:

1. Wrong model
2. Wrong API key
3. Very low timeout
4. Invalid JSON/body
5. Oversized prompt
6. Upstream unavailable, manual test
7. Rate limit, if wrapper configured
8. Fallback, if wrapper configured with secondary provider/key

For each failure, record:

```text
client exception type
http status code
response body
gateway error shape
does request appear in logs?
does retry/fallback happen?
```

---

## 13. Security and privacy

Do not hardcode real API keys.

Rules:

* Read secrets from `.env`.
* Mask base URLs and keys in UI where needed.
* Never print full API keys.
* In exports, do not include API keys.
* Make response text storage configurable.
* Make stream event storage configurable.
* Default:

  * Store metadata
  * Store output text
  * Do not store full raw prompts unless enabled
* Add UI warning when prompt/response storage is enabled.

---

## 14. CLI support

In addition to the Streamlit app, provide CLI scripts.

### `scripts/init_db.py`

Creates DB tables.

Usage:

```bash
python scripts/init_db.py
```

### `scripts/run_cli_benchmark.py`

Runs benchmark without UI.

Usage:

```bash
python scripts/run_cli_benchmark.py \
  --targets configs/targets.yaml \
  --prompts configs/prompts.yaml \
  --profiles configs/test_profiles.yaml \
  --profile quick \
  --run-name "quick-litellm-bifrost-test"
```

### `scripts/export_latest.py`

Exports latest run.

Usage:

```bash
python scripts/export_latest.py --output results/
```

---

## 15. `pyproject.toml`

Use `uv`-friendly project setup.

Dependencies:

```toml
[project]
name = "llm-wrapper-bench"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "streamlit>=1.36.0",
    "httpx>=0.27.0",
    "openai>=1.0.0",
    "pydantic>=2.0.0",
    "pydantic-settings>=2.0.0",
    "pandas>=2.0.0",
    "numpy>=1.26.0",
    "plotly>=5.0.0",
    "sqlalchemy>=2.0.0",
    "aiosqlite>=0.19.0",
    "pyyaml>=6.0.0",
    "python-dotenv>=1.0.0",
    "tenacity>=8.0.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "ruff>=0.5.0",
    "mypy>=1.0.0",
]
```

Commands:

```bash
uv venv
uv pip install -e ".[dev]"
python scripts/init_db.py
streamlit run app/main.py
```

---

## 16. README content

README must explain:

1. What this project does
2. Why direct vLLM baseline is required
3. How to configure targets
4. How to configure prompts
5. How to run webapp
6. How to run CLI benchmark
7. How TTFT is measured
8. How to interpret wrapper overhead
9. How to use logging checklist
10. Limitations

Important limitations to include:

```text
- TTFT is affected by vLLM queueing, GPU load, prompt length, and network.
- Wrapper overhead may be small compared to model generation time.
- Run multiple repetitions and compare percentiles, not one request.
- Logging/caching can change latency.
- Some logging capabilities require manual verification in wrapper dashboards.
- Some wrappers may buffer streaming chunks, affecting TTFT.
- Model quality is not compared because every target uses the same upstream model.
```

---

## 17. Acceptance criteria

The project is complete when:

1. User can define multiple OpenAI-compatible targets in YAML.
2. User can run Streamlit webapp.
3. User can validate target health through `/models` and a small chat request.
4. User can run benchmark with selected targets/prompts/profile.
5. App measures:

   * TTFT
   * Total latency
   * First raw chunk time
   * First content chunk time
   * Chunk count
   * Output length
   * Error/timeout status
6. App persists all request results in SQLite.
7. App shows summary tables and charts.
8. App computes wrapper overhead against `direct_vllm`.
9. App can export CSV/JSONL/Markdown reports.
10. App can run capability tests and show matrix.
11. App has editable logging checklist.
12. API keys are never exposed in UI or exports.
13. Project can also run from CLI.
14. Code is modular and testable.
15. Basic unit tests exist for config loading and metric calculation.

---

## 18. Implementation order

Build in this order:

### Step 1: Skeleton

* Create project structure.
* Add `pyproject.toml`.
* Add README.
* Add example configs.
* Add `.env.example`.

### Step 2: Config loading

* Implement YAML loading.
* Implement env var substitution.
* Implement Pydantic validation.
* Add tests.

### Step 3: SQLite DB

* Implement SQLAlchemy models.
* Implement init script.
* Implement insert/read helpers.

### Step 4: Streaming HTTP client

* Implement OpenAI-compatible streaming call with `httpx`.
* Parse SSE.
* Measure TTFT/latency.
* Test against direct vLLM target.

### Step 5: Benchmark runner

* Implement repetitions and concurrency.
* Persist each result immediately.
* Add progress callback.

### Step 6: Streamlit run page

* Select configs/targets/prompts/profile.
* Start benchmark.
* Show progress.

### Step 7: Results page

* Load runs from DB.
* Show summary table.
* Add charts.
* Add overhead vs direct baseline.

### Step 8: Capability tests

* Implement health/model list/basic chat/streaming/error tests.
* Show matrix.

### Step 9: Logging checklist

* Editable table.
* Save to DB.
* Export matrix.

### Step 10: Export

* CSV exports.
* Markdown report.
* Raw JSONL export.

### Step 11: Polish

* Better error messages.
* API key masking.
* README examples.
* Tests.

---

## 19. Example benchmark interpretation

The app should help the user reach conclusions like:

```text
Direct vLLM:
  TTFT P50: 420 ms
  Total latency P50: 4.2 s

LiteLLM:
  TTFT P50: 455 ms
  Overhead: +35 ms / +8.3%
  Total latency P50: 4.3 s
  Logging: strong callback/export support
  Capabilities: streaming pass, extra_body pass, model list pass

Bifrost:
  TTFT P50: 440 ms
  Overhead: +20 ms / +4.7%
  Total latency P50: 4.25 s
  Logging: strong built-in LogStore/Prometheus/OTel
  Capabilities: streaming pass, extra_body partial, model list pass
```

Do not hardcode these numbers. They are example report style only.

---

## 20. Important coding details

Use monotonic time:

```python
time.perf_counter()
```

Do not use wall-clock datetime for latency.

Use timezone-aware datetime for DB timestamps.

Save results even on error.

Use `return_exceptions=True` when gathering concurrent tasks.

Use clear exception classes or error types:

```text
http_error
timeout
connection_error
sse_parse_error
empty_response
unknown_error
```

Normalize base URLs:

```python
base_url.rstrip("/")
```

If base URL ends with `/v1`, chat endpoint is:

```text
{base_url}/chat/completions
```

If base URL does not end with `/v1`, optionally append `/v1`, but make this behavior configurable.

Recommended function:

```python
def build_chat_completions_url(base_url: str) -> str:
    base = base_url.rstrip("/")
    if base.endswith("/v1"):
        return f"{base}/chat/completions"
    return f"{base}/v1/chat/completions"
```

But allow target config:

```yaml
base_url: "http://localhost:4000/v1"
```

That should work cleanly.

---

## 21. Deliverables

Produce a complete runnable repository with:

```text
- Streamlit webapp
- Async benchmark engine
- SQLite persistence
- Example configs
- CLI benchmark runner
- CSV/JSONL/Markdown exports
- Capability matrix
- Logging checklist
- README
- Unit tests
```

The final app should answer:

```text
Which wrapper adds the least TTFT overhead?
Which wrapper adds the least total latency overhead?
Which wrapper handles streaming cleanly?
Which wrapper has the best logging/observability for our needs?
Which wrapper preserves OpenAI/vLLM capabilities best?
Which wrapper behaves best under concurrency?
Which wrapper fails cleanly?
```
