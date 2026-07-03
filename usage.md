# USAGE.md

## 1. What this project does

This project is a Python Streamlit webapp for benchmarking LLM wrappers/gateways against the same OpenAI-compatible Qwen vLLM endpoint.

The benchmark app is not the gateway.

The architecture is:

```text
Python Streamlit benchmark app
   |-- Direct vLLM endpoint
   |-- LiteLLM Proxy service
   |-- Bifrost Gateway service
   |-- Portkey Gateway service
   |-- Helicone AI Gateway service
   `-- LLM Gateway service
```

Every service is tested through an OpenAI-compatible API, usually:

```text
/v1/chat/completions
```

The app measures:

```text
TTFT
total latency
streaming chunk behavior
tokens/sec
errors
timeouts
capability support
logging/observability differences
```

---

## 2. Prerequisites

You need:

```text
Python 3.11+
uv or pip
network access to your Qwen vLLM endpoint
optional Docker/Podman
optional Node/npm/npx
```

Your vLLM endpoint should already expose an OpenAI-compatible API.

Example:

```text
https://YOUR_VLLM_ROUTE/v1/chat/completions
```

Set common environment variables:

```bash
export DIRECT_VLLM_BASE_URL="https://YOUR_VLLM_ROUTE/v1"
export DIRECT_VLLM_API_KEY="dummy-or-real-key"
export VLLM_MODEL="qwen3-6"
```

If your vLLM endpoint does not require auth, use:

```bash
export DIRECT_VLLM_API_KEY="dummy"
```

---

## 3. Run the benchmark webapp

Install project dependencies:

```bash
uv venv
uv pip install -e ".[dev]"
```

Initialize database:

```bash
python scripts/init_db.py
```

Run Streamlit:

```bash
streamlit run app/main.py
```

Open the app in browser.

Usually:

```text
http://localhost:8501
```

---

## 4. Direct vLLM baseline

No extra service is needed.

Test direct vLLM first:

```bash
curl -X POST "${DIRECT_VLLM_BASE_URL}/chat/completions" \
  -H "Authorization: Bearer ${DIRECT_VLLM_API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen3-6",
    "messages": [{"role": "user", "content": "Say OK"}],
    "stream": false
  }'
```

Add this target:

```yaml
- id: direct_vllm
  name: Direct vLLM Baseline
  enabled: true
  mode: openai_http
  kind: baseline
  base_url: "${DIRECT_VLLM_BASE_URL}"
  api_key_env: "DIRECT_VLLM_API_KEY"
  model: "qwen3-6"
  setup_required: false
```

Use this as the baseline for overhead calculations.

---

## 5. LiteLLM Proxy

LiteLLM can be used as a Python SDK or as a proxy service. For this benchmark, use the proxy service because that tests real gateway behavior.

LiteLLM Proxy supports OpenAI-compatible routing and vLLM/OpenAI-compatible hosted endpoints. LiteLLM docs describe CLI and Docker proxy startup, and vLLM support uses `hosted_vllm/<model-name>`. Sources: LiteLLM Proxy quickstart and LiteLLM vLLM provider docs.

### 5.1 Create config

Create:

```text
services/litellm/litellm_config.yaml
```

Content:

```yaml
model_list:
  - model_name: qwen3-6
    litellm_params:
      model: hosted_vllm/qwen3-6
      api_base: os.environ/DIRECT_VLLM_BASE_URL
      api_key: os.environ/DIRECT_VLLM_API_KEY

general_settings:
  master_key: os.environ/LITELLM_MASTER_KEY
```

### 5.2 Run with Python/uv

```bash
export DIRECT_VLLM_BASE_URL="https://YOUR_VLLM_ROUTE/v1"
export DIRECT_VLLM_API_KEY="dummy-or-real-key"
export LITELLM_MASTER_KEY="sk-litellm-test"

uv pip install "litellm[proxy]"
litellm --config services/litellm/litellm_config.yaml --port 4000
```

### 5.3 Or run with Docker

```bash
export DIRECT_VLLM_BASE_URL="https://YOUR_VLLM_ROUTE/v1"
export DIRECT_VLLM_API_KEY="dummy-or-real-key"
export LITELLM_MASTER_KEY="sk-litellm-test"

docker run --rm \
  -p 4000:4000 \
  -v "$(pwd)/services/litellm/litellm_config.yaml:/app/config.yaml" \
  -e DIRECT_VLLM_BASE_URL="${DIRECT_VLLM_BASE_URL}" \
  -e DIRECT_VLLM_API_KEY="${DIRECT_VLLM_API_KEY}" \
  -e LITELLM_MASTER_KEY="${LITELLM_MASTER_KEY}" \
  docker.litellm.ai/berriai/litellm:latest \
  --config /app/config.yaml
```

### 5.4 Test LiteLLM

```bash
curl -X POST "http://localhost:4000/v1/chat/completions" \
  -H "Authorization: Bearer sk-litellm-test" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen3-6",
    "messages": [{"role": "user", "content": "Say OK"}],
    "stream": false
  }'
```

### 5.5 Add target

```yaml
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
```

---

## 6. Bifrost

Bifrost is not a Python import. Run it as a separate gateway service.

Bifrost docs show Docker and NPX startup, and Bifrost has a vLLM provider configuration where you set the vLLM URL and exact model name.

### 6.1 Run with Docker

```bash
mkdir -p services/bifrost/data

docker run --rm \
  -p 8080:8080 \
  -v "$(pwd)/services/bifrost/data:/app/data" \
  maximhq/bifrost
```

### 6.2 Or run with NPX

```bash
npx -y @maximhq/bifrost
```

### 6.3 Configure provider

Open:

```text
http://localhost:8080
```

In the UI, add/configure a provider:

```text
Provider: vLLM
vLLM URL: https://YOUR_VLLM_ROUTE
or: https://YOUR_VLLM_ROUTE/v1
Model Name: qwen3-6
API Key: dummy-or-real-key
```

If your endpoint needs bearer auth, paste the token or configure environment variable support in Bifrost.

### 6.4 Test Bifrost

Try this first:

```bash
curl -X POST "http://localhost:8080/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "vllm/qwen3-6",
    "messages": [{"role": "user", "content": "Say OK"}],
    "stream": false
  }'
```

If that model name fails, check the exact model alias shown/configured in the Bifrost UI and update the request.

### 6.5 Add target

```yaml
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
```

If Bifrost does not require an API key locally, set:

```bash
export BIFROST_API_KEY="dummy"
```

---

## 7. Portkey Gateway

Portkey can run locally with NPX or Docker. Its gateway runs on:

```text
http://localhost:8787/v1
```

Portkey custom hosts can route requests to privately hosted or local model endpoints in hybrid or air-gapped enterprise deployments. On SaaS, private/internal URLs are not supported unless reachable publicly.

### 7.1 Run with NPX

```bash
npx @portkey-ai/gateway
```

Expected local endpoint:

```text
http://localhost:8787/v1
```

Expected console:

```text
http://localhost:8787/public/
```

### 7.2 Or run with Docker

```bash
docker run --rm \
  -p 8787:8787 \
  portkeyai/gateway:latest
```

### 7.3 Test Portkey with custom host

This depends on whether your Portkey setup allows custom internal hosts.

```bash
curl -X POST "http://localhost:8787/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -H "x-portkey-provider: openai" \
  -H "x-portkey-custom-host: ${DIRECT_VLLM_BASE_URL}" \
  -H "Authorization: Bearer ${DIRECT_VLLM_API_KEY}" \
  -d '{
    "model": "qwen3-6",
    "messages": [{"role": "user", "content": "Say OK"}],
    "stream": false
  }'
```

If this fails:

1. Check whether custom hosts are enabled.
2. Check whether the gateway allows your internal hostname.
3. Check whether the vLLM route is reachable from the Portkey container/process.
4. Check whether Portkey expects a different auth header split between Portkey key and provider key.

### 7.4 Add target

```yaml
- id: portkey_local
  name: Portkey Gateway Local
  enabled: false
  mode: openai_http
  kind: service_gateway
  base_url: "http://localhost:8787/v1"
  api_key_env: "DIRECT_VLLM_API_KEY"
  model: "qwen3-6"
  provider: "openai"
  custom_host: "${DIRECT_VLLM_BASE_URL}"
  headers:
    x-portkey-provider: "openai"
    x-portkey-custom-host: "${DIRECT_VLLM_BASE_URL}"
  setup_required: true
  setup_doc_section: "Portkey Gateway"
```

---

## 8. Helicone AI Gateway

Helicone provides an OpenAI-compatible AI Gateway and a Docker quick start for the gateway. For private vLLM endpoints, verify whether you are using hosted Helicone, self-hosted Helicone, or the standalone gateway image.

Important:

```text
If your vLLM endpoint is internal-only, a hosted gateway probably cannot reach it.
Use self-hosted/local gateway mode if possible.
```

### 8.1 Run standalone Docker gateway

Use a different local port if Bifrost already uses `8080`.

```bash
docker run --rm \
  -p 8081:8080 \
  helicone/ai-gateway
```

Local endpoint:

```text
http://localhost:8081
```

### 8.2 Test Helicone

The exact provider/custom-host configuration may depend on the current Helicone gateway config. Start with the documented OpenAI-compatible format and adjust based on your gateway config.

```bash
curl -X POST "http://localhost:8081/v1/chat/completions" \
  -H "Authorization: Bearer ${HELICONE_API_KEY:-dummy}" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen3-6",
    "messages": [{"role": "user", "content": "Say OK"}],
    "stream": false
  }'
```

If using hosted Helicone:

```text
base_url: https://ai-gateway.helicone.ai
```

but hosted Helicone must be able to reach your provider, so internal vLLM may not work.

### 8.3 Add target

```yaml
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
```

---

## 9. LLM Gateway

LLM Gateway is a self-hostable OpenAI-compatible gateway. Its Docker docs describe a single-container setup bundling UI, API, Gateway, PostgreSQL, and Redis for quick tests.

### 9.1 Run with Docker

Check the official LLM Gateway Docker docs for the latest image name and required env vars.

Example placeholder:

```bash
docker run --rm \
  -p 3000:3000 \
  -e DATABASE_URL="postgresql://..." \
  -e REDIS_URL="redis://..." \
  llmgateway/llmgateway:latest
```

If using the single-container all-in-one image from official docs, use that exact image and port instead.

### 9.2 Configure provider

In the LLM Gateway UI/config, add an OpenAI-compatible provider:

```text
Provider type: OpenAI-compatible
Base URL: https://YOUR_VLLM_ROUTE/v1
API key: dummy-or-real-key
Model: qwen3-6
```

### 9.3 Test LLM Gateway

```bash
curl -X POST "http://localhost:3000/v1/chat/completions" \
  -H "Authorization: Bearer ${LLM_GATEWAY_API_KEY:-dummy}" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen3-6",
    "messages": [{"role": "user", "content": "Say OK"}],
    "stream": false
  }'
```

### 9.4 Add target

```yaml
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
```

---

## 10. Optional: LiteLLM SDK import mode

This is not a real service benchmark. Use it only if your work environment does not allow local services, Docker, or Node.

Install:

```bash
uv pip install litellm
```

Target:

```yaml
- id: litellm_sdk
  name: LiteLLM SDK Import
  enabled: false
  mode: python_sdk
  kind: sdk_wrapper
  base_url: "${DIRECT_VLLM_BASE_URL}"
  api_key_env: "DIRECT_VLLM_API_KEY"
  model: "hosted_vllm/qwen3-6"
  setup_required: false
```

This tests Python wrapper overhead only. It does not test:

```text
central gateway logs
virtual keys
shared budgets
team-level rate limits
dashboard behavior
production gateway overhead
```

---

## 11. Optional managed/infrastructure gateways

### 11.1 Cloudflare AI Gateway

Cloudflare AI Gateway supports custom providers over HTTPS and OpenAI-compatible chat completion endpoints.

Use only if:

```text
Your vLLM endpoint is HTTPS-reachable by Cloudflare
or your company approves exposing/routing it through Cloudflare
```

Not recommended for internal-only vLLM without approval.

### 11.2 Vercel AI Gateway

Vercel AI Gateway supports OpenAI-compatible APIs and can be used by changing base URL/API key.

Use only if:

```text
Your model/provider is available through Vercel
or your company accepts managed gateway use
```

### 11.3 Kong AI Gateway

Kong AI Gateway is infrastructure/API-gateway style.

Use only if your company already runs Kong or allows deploying Kong locally/inside Kubernetes.

### 11.4 Envoy AI Gateway

Envoy AI Gateway is Kubernetes/Envoy Gateway based.

Use only if you have Kubernetes/OpenShift access and want production-style infra testing.

### 11.5 Azure API Management AI Gateway

Azure API Management can import OpenAI-compatible LLM APIs and apply gateway policies.

Use only if your company uses Azure APIM or you have permissions to create/import APIs.

---

## 12. Recommended test order

Use this order:

```text
1. direct_vllm
2. litellm_proxy
3. bifrost
4. portkey_local
5. helicone_gateway
6. llm_gateway
7. optional managed/infrastructure gateways
```

Do not benchmark everything at once first.

First make each service answer with curl.

Then add it to `targets.yaml`.

Then validate in the Streamlit UI.

Then run the benchmark.

---

## 13. Benchmark workflow

For each service:

```text
1. Start service.
2. Curl-test service.
3. Add/update target in configs/targets.yaml.
4. Open Streamlit app.
5. Go to Targets Config page.
6. Validate target.
7. Go to Run Benchmark page.
8. Select direct_vllm and one wrapper.
9. Run quick profile.
10. If successful, run standard profile.
11. Fill Logging Checklist manually.
12. Export report.
```

---

## 14. Troubleshooting

### Service cannot reach vLLM

From inside Docker, `localhost` means the container itself, not your host machine.

If vLLM is on your host machine, use:

```text
host.docker.internal
```

or the real internal network route.

Example:

```bash
export DIRECT_VLLM_BASE_URL="http://host.docker.internal:8000/v1"
```

On Linux, you may need:

```bash
docker run --add-host=host.docker.internal:host-gateway ...
```

### SSL/certificate error

If work uses internal TLS certificates, Docker containers may not trust the company CA.

Options:

```text
Use trusted route/cert
Mount company CA into container
Configure REQUESTS_CA_BUNDLE / SSL_CERT_FILE if supported
Avoid -k for benchmark numbers unless only smoke-testing
```

### Port already in use

Change host port:

```bash
docker run -p 8081:8080 maximhq/bifrost
```

Then target base URL becomes:

```yaml
base_url: "http://localhost:8081/v1"
```

### Gateway answers but benchmark fails

Check:

```text
model name mismatch
missing Authorization header
wrong /v1 path
wrapper-specific headers missing
streaming unsupported or buffered
timeout too low
```

### Curl works but Streamlit does not

Check that the same env vars are visible to the Streamlit process:

```bash
echo $DIRECT_VLLM_BASE_URL
echo $DIRECT_VLLM_API_KEY
streamlit run app/main.py
```

### Docker not allowed at work

Use:

```text
LiteLLM CLI through Python/uv
LiteLLM SDK import mode
Direct vLLM baseline only
```

Bifrost/Portkey/Helicone/LLM Gateway may need Docker, Node, or server deployment.

---

## 15. Final note

For fair results, compare:

```text
direct_vllm vs one wrapper at a time
```

Keep constant:

```text
same prompt
same model
same max_tokens
same temperature
same stream setting
same concurrency
same network path
same vLLM load
```

The wrapper is the only thing that should change.
