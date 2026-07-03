# UPDATE_PLAN.md

## Goal

Update the Python Streamlit benchmark webapp so it can compare multiple LLM wrapper/gateway services against the same internal OpenAI-compatible Qwen vLLM endpoint.

The app must support:

1. Direct vLLM baseline.
2. Local/self-hosted gateway services:

   * LiteLLM Proxy
   * Bifrost
   * Portkey Gateway
   * Helicone AI Gateway
   * LLM Gateway
3. Optional managed or infrastructure gateways:

   * Cloudflare AI Gateway
   * Kong AI Gateway
   * Envoy AI Gateway
   * Vercel AI Gateway
   * TrueFoundry AI Gateway
   * Azure API Management AI Gateway
4. Optional SDK/import wrappers:

   * LiteLLM SDK
   * LangChain wrapper
   * LlamaIndex wrapper

The final webapp must not assume that the wrappers are Python imports. Most wrappers should be treated as external OpenAI-compatible HTTP targets.

---

## 1. Update target concept

Replace the old simple target model with a richer target model.

### Target modes

Support these target modes:

```text
openai_http
python_sdk
managed_gateway
manual_only
```

### Meaning

```text
openai_http:
  A service exposing /v1/chat/completions.
  Examples: direct vLLM, LiteLLM Proxy, Bifrost, Portkey Gateway, Helicone Gateway, LLM Gateway.

python_sdk:
  A Python import/wrapper used inside the benchmark process.
  Examples: LiteLLM SDK, LangChain, LlamaIndex.

managed_gateway:
  A cloud/SaaS gateway requiring external account/API key.
  Examples: Cloudflare AI Gateway, Vercel AI Gateway.

manual_only:
  A target that is too infrastructure-heavy for automatic setup but can be documented.
  Examples: Kong AI Gateway, Envoy AI Gateway, Azure API Management.
```

---

## 2. Update `TargetConfig`

In `bench/schemas.py`, update `TargetConfig`:

```python
class TargetConfig(BaseModel):
    id: str
    name: str
    enabled: bool = True

    mode: Literal[
        "openai_http",
        "python_sdk",
        "managed_gateway",
        "manual_only",
    ] = "openai_http"

    kind: Literal[
        "baseline",
        "service_gateway",
        "sdk_wrapper",
        "managed_gateway",
        "infra_gateway",
        "other",
    ] = "service_gateway"

    base_url: str | None = None
    api_key_env: str | None = None
    api_key: str | None = None
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
```

---

## 3. Update example targets config

Create:

```text
configs/targets.example.yaml
```

with this structure:

```yaml
targets:
  - id: direct_vllm
    name: Direct vLLM Baseline
    enabled: true
    mode: openai_http
    kind: baseline
    base_url: "${DIRECT_VLLM_BASE_URL}"
    api_key_env: "DIRECT_VLLM_API_KEY"
    model: "qwen3-6"
    setup_required: false
    notes: "Direct OpenAI-compatible vLLM endpoint."

  - id: litellm_proxy
    name: LiteLLM Proxy
    enabled: true
    mode: openai_http
    kind: service_gateway
    base_url: "http://localhost:4000/v1"
    api_key_env: "LITELLM_MASTER_KEY"
    model: "qwen3-6"
    setup_required: true
    setup_doc_section: "LiteLLM Proxy"

  - id: bifrost
    name: Bifrost Gateway
    enabled: true
    mode: openai_http
    kind: service_gateway
    base_url: "http://localhost:8080/v1"
    api_key_env: "BIFROST_API_KEY"
    model: "vllm/qwen3-6"
    setup_required: true
    setup_doc_section: "Bifrost"

  - id: portkey_local
    name: Portkey Gateway Local
    enabled: false
    mode: openai_http
    kind: service_gateway
    base_url: "http://localhost:8787/v1"
    api_key_env: "PORTKEY_PROVIDER_API_KEY"
    model: "qwen3-6"
    provider: "openai"
    custom_host: "${DIRECT_VLLM_BASE_URL}"
    headers:
      x-portkey-provider: "openai"
      x-portkey-custom-host: "${DIRECT_VLLM_BASE_URL}"
    setup_required: true
    setup_doc_section: "Portkey Gateway"

  - id: helicone_gateway
    name: Helicone AI Gateway
    enabled: false
    mode: openai_http
    kind: service_gateway
    base_url: "http://localhost:8081/v1"
    api_key_env: "HELICONE_API_KEY"
    model: "qwen3-6"
    setup_required: true
    setup_doc_section: "Helicone AI Gateway"

  - id: llm_gateway
    name: LLM Gateway
    enabled: false
    mode: openai_http
    kind: service_gateway
    base_url: "http://localhost:3000/v1"
    api_key_env: "LLM_GATEWAY_API_KEY"
    model: "qwen3-6"
    setup_required: true
    setup_doc_section: "LLM Gateway"

  - id: litellm_sdk
    name: LiteLLM SDK Import
    enabled: false
    mode: python_sdk
    kind: sdk_wrapper
    model: "hosted_vllm/qwen3-6"
    api_key_env: "DIRECT_VLLM_API_KEY"
    base_url: "${DIRECT_VLLM_BASE_URL}"
    setup_required: false
    notes: "Tests LiteLLM as a Python import, not as a real gateway service."
```

---

## 4. Add service setup folder

Add this folder:

```text
services/
  README.md

  litellm/
    litellm_config.yaml
    run_litellm.sh
    test_litellm.sh

  bifrost/
    run_bifrost_docker.sh
    run_bifrost_npx.sh
    test_bifrost.sh
    data/

  portkey/
    run_portkey_docker.sh
    run_portkey_npx.sh
    test_portkey.sh

  helicone/
    run_helicone_gateway_docker.sh
    test_helicone_gateway.sh

  llm_gateway/
    run_llm_gateway_docker.sh
    test_llm_gateway.sh

  docker-compose.example.yml
```

The Python webapp does not start these automatically in v1. It only validates whether they are running.

---

## 5. Add target healthcheck page improvements

Update `05_Targets_Config.py`.

For each target, show:

```text
Target name
Mode
Base URL
Model
API key env var exists? yes/no
Setup required? yes/no
Service reachable? yes/no
/models works? yes/no
Small chat test works? yes/no
Streaming chat test works? yes/no
```

Add buttons:

```text
Validate selected target
Validate all enabled targets
Copy curl test command
Show setup instructions
```

Healthcheck logic:

1. If `mode=openai_http`, call:

   * `GET {base_url}/models`
   * `POST {base_url}/chat/completions`
   * `POST {base_url}/chat/completions` with `stream=true`

2. If `mode=python_sdk`, run its SDK-specific smoke test.

3. If `mode=manual_only`, do not test automatically. Show setup notes.

---

## 6. Add service setup status to UI

On the Run Benchmark page, before running:

```text
Do not run benchmark until all selected openai_http targets pass healthcheck.
```

Show warning:

```text
LiteLLM/Bifrost/Portkey/etc. must already be running as services. This webapp does not start them.
```

Add status colors:

```text
green: target validated
yellow: target reachable but chat test failed
red: not reachable
gray: not tested
```

---

## 7. Add wrapper registry

Create:

```text
bench/wrapper_registry.py
```

Include static metadata for known wrappers:

```python
KNOWN_WRAPPERS = {
    "direct_vllm": {
        "category": "baseline",
        "default_port": None,
        "setup": "Already running upstream endpoint.",
        "docs": "vLLM OpenAI-compatible server",
    },
    "litellm_proxy": {
        "category": "service_gateway",
        "default_port": 4000,
        "setup": "Run LiteLLM Proxy with litellm_config.yaml.",
        "supports_local_python_service": True,
        "supports_docker": True,
    },
    "bifrost": {
        "category": "service_gateway",
        "default_port": 8080,
        "setup": "Run Bifrost by Docker or NPX and configure vLLM provider in UI.",
        "supports_docker": True,
        "supports_npx": True,
    },
    "portkey_local": {
        "category": "service_gateway",
        "default_port": 8787,
        "setup": "Run Portkey Gateway by Docker or NPX, then pass custom host headers.",
        "supports_docker": True,
        "supports_npx": True,
    },
    "helicone_gateway": {
        "category": "service_gateway",
        "default_port": 8081,
        "setup": "Run Helicone AI Gateway Docker image or hosted gateway.",
        "supports_docker": True,
    },
    "llm_gateway": {
        "category": "service_gateway",
        "default_port": 3000,
        "setup": "Run LLM Gateway Docker/self-host setup.",
        "supports_docker": True,
    },
}
```

Use this only for UI display and default templates. The actual benchmark must still be driven by YAML config.

---

## 8. Update benchmark runner

The benchmark runner must support:

```text
openai_http targets:
  run through raw httpx streaming client.

python_sdk targets:
  run through SDK-specific adapter.

managed_gateway targets:
  same as openai_http, but show warning that external network/account is involved.

manual_only targets:
  cannot be benchmarked until converted into openai_http target.
```

Add adapter interface:

```python
class TargetAdapter(Protocol):
    async def healthcheck(self, target: TargetConfig) -> HealthcheckResult:
        ...

    async def run_streaming_chat(
        self,
        target: TargetConfig,
        prompt: PromptConfig,
        profile: TestProfile,
        client_request_id: str,
    ) -> RequestMeasurement:
        ...
```

Implement:

```text
OpenAIHTTPAdapter
LiteLLMSDKAdapter
```

Later adapters can be added, but most wrappers should use `OpenAIHTTPAdapter`.

---

## 9. Update request headers support

Some gateways require provider-specific headers.

The HTTP adapter must merge:

```text
Authorization: Bearer <api_key>
Content-Type: application/json
x-client-request-id: <uuid>
target.headers
```

Important:

* Do not log full API keys.
* Do log which headers were sent, but redact sensitive values.
* Allow headers to use env substitution.

Example:

```yaml
headers:
  x-portkey-provider: "openai"
  x-portkey-custom-host: "${DIRECT_VLLM_BASE_URL}"
```

---

## 10. Update capability matrix

Add capability tests grouped into two groups.

### Client/API compatibility tests

```text
/models
basic chat
streaming chat
stream_options.include_usage
system prompt
long prompt
bad model error
timeout behavior
extra_body passthrough
custom headers sent
```

### Gateway/service features

These may be manual or semi-automated:

```text
virtual keys
provider key management
logging dashboard
prompt redaction
response redaction
cost tracking
token tracking
rate limiting
fallback
load balancing
caching
prometheus
opentelemetry
request id correlation
```

For gateway/service features, allow status:

```text
pass
fail
partial
manual
unknown
not_applicable
```

---

## 11. Update logging checklist

Add one row per known wrapper and one column per feature.

Features:

```text
request_id
client_request_id_preserved
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
dashboard_ui
log_search
log_retention_config
```

Add an evidence field:

```text
Evidence:
  e.g. "Seen in LiteLLM UI"
  e.g. "Bifrost LogStore shows request"
  e.g. "Portkey console shows trace"
  e.g. "Prometheus /metrics reachable"
```

The app should not pretend to verify dashboard-only features automatically.

---

## 12. Add `USAGE.md`

Add a full usage file that explains:

1. How to run the Python benchmark app.
2. How to run direct vLLM baseline.
3. How to run LiteLLM Proxy.
4. How to run Bifrost.
5. How to run Portkey Gateway.
6. How to run Helicone AI Gateway.
7. How to run LLM Gateway.
8. How to add each one to `targets.yaml`.
9. How to curl-test before benchmarking.
10. What to do if work env blocks Docker/Node/local ports.

---

## 13. Add service test command generator

In the UI, add “Copy curl test” for each target.

For a target:

```yaml
base_url: http://localhost:4000/v1
api_key: sk-test
model: qwen3-6
```

Generate:

```bash
curl -X POST "http://localhost:4000/v1/chat/completions" \
  -H "Authorization: Bearer sk-test" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen3-6",
    "messages": [{"role": "user", "content": "Say OK"}],
    "stream": false
  }'
```

If target has extra headers, include them.

---

## 14. Add service assumptions section to README

Add this important explanation:

```text
The benchmark app does not install or start LiteLLM, Bifrost, Portkey, Helicone, or LLM Gateway.

Those wrappers must be started separately as HTTP services. Once running, they are added to configs/targets.yaml as OpenAI-compatible endpoints.

The benchmark app then treats them like any other /v1/chat/completions API.
```

---

## 15. Final expected workflow

The user workflow should be:

```text
1. Start direct vLLM endpoint or confirm it already exists.
2. Start one wrapper service, e.g. LiteLLM Proxy.
3. Test the wrapper with curl.
4. Add wrapper URL to configs/targets.yaml.
5. Open Streamlit app.
6. Validate targets.
7. Run benchmark.
8. Check Results page.
9. Fill Logging Checklist based on wrapper dashboard/logs.
10. Export report.
```

---

## 16. Acceptance criteria update

The updated app is acceptable when:

1. It can benchmark direct vLLM.
2. It can benchmark LiteLLM Proxy through `http://localhost:4000/v1`.
3. It can benchmark Bifrost through `http://localhost:8080/v1`.
4. It can benchmark any additional OpenAI-compatible gateway by YAML only.
5. It can optionally test LiteLLM SDK import separately.
6. It clearly shows which wrappers require external service setup.
7. It provides setup docs in `USAGE.md`.
8. It never assumes Bifrost/Portkey/Helicone are Python imports.
9. It supports wrapper-specific headers.
10. It provides curl test commands.
11. It persists benchmark results even if one service fails.
12. It shows direct-vLLM baseline overhead for each wrapper.
