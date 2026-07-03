# LLM Wrapper Benchmark

This project is a Python web application for benchmarking OpenAI-compatible LLM wrappers and gateways against the same upstream vLLM/Qwen endpoint. It compares wrapper overhead and behavior, not model quality.

The app measures latency and streaming behavior, tracks request results in SQLite, runs capability checks, and provides a manual logging checklist for wrapper observability features.

The benchmark app does not install or start LiteLLM, Bifrost, Portkey, Helicone, or LLM Gateway. Those wrappers must be started separately as HTTP services. Once running, add them to `configs/targets.yaml` as OpenAI-compatible endpoints, and the benchmark app treats them like any other `/v1/chat/completions` API.

## Why Use A Direct vLLM Baseline

Every wrapper should be compared against a direct call to the same vLLM endpoint. Keep prompts, model alias, temperature, `max_tokens`, timeout, concurrency, and repetitions constant. The target `base_url`, API key, headers, and wrapper-specific model alias are the only variables that should change.

Without the direct baseline, wrapper overhead cannot be separated from vLLM queueing, GPU load, prompt length, and network variance.

## Install

```bash
uv venv
uv pip install -e ".[dev]"
```

Regular `pip` also works:

```bash
python -m pip install -e ".[dev]"
```

## Configure Targets

Copy the example files and edit the copies:

```bash
cp .env.example .env
cp configs/targets.example.yaml configs/targets.yaml
cp configs/prompts.example.yaml configs/prompts.yaml
cp configs/test_profiles.example.yaml configs/test_profiles.yaml
```

Targets are OpenAI-compatible endpoints:

```yaml
targets:
  - id: direct_vllm
    name: Direct vLLM Baseline
    mode: openai_http
    kind: baseline
    base_url: "${DIRECT_VLLM_BASE_URL}"
    api_key_env: "DIRECT_VLLM_API_KEY"
    model: "qwen3-6"
```

Environment placeholders such as `${DIRECT_VLLM_BASE_URL}` are resolved from `.env` or the process environment. API keys are read from environment variables and are not exported.

Most wrappers should be configured as external `openai_http` targets. Use `python_sdk` only for explicit import-wrapper tests such as LiteLLM SDK, and use `manual_only` for infrastructure-heavy gateways until you deploy them behind a concrete OpenAI-compatible base URL.

For wrapper startup examples and curl smoke tests, see [USAGE.md](USAGE.md).

## Configure Prompts

Prompts are YAML records with OpenAI-style chat messages. Long prompts can use `repeat_user_content` to repeat the last user message content without writing a huge YAML file.

## Run The Web App

```bash
python scripts/init_db.py
streamlit run app/main.py
```

The app includes pages for running benchmarks, viewing results, checking capabilities, editing the logging checklist, validating targets, and inspecting raw events.

## Run From CLI

```bash
python scripts/run_cli_benchmark.py \
  --targets configs/targets.yaml \
  --prompts configs/prompts.yaml \
  --profiles configs/test_profiles.yaml \
  --profile quick \
  --run-name "quick-litellm-bifrost-test"
```

Export the latest run:

```bash
python scripts/export_latest.py --output results/
```

## TTFT Measurement

TTFT is measured only in streaming mode. The benchmark records:

- `request_started_at`: immediately before sending the HTTP request.
- `first_chunk_ms`: first raw SSE data event, even if it contains no generated text.
- `first_content_chunk_ms`: first SSE event with non-empty generated text.
- `ttft_ms`: equal to `first_content_chunk_ms`.
- `total_latency_ms`: stream completion time minus request start.

Inter-token values are reported as content chunk latency unless tokenizer-level token IDs are available.

## Interpreting Wrapper Overhead

Summary metrics are grouped by run, target, prompt, and concurrency level. Overhead is computed against `direct_vllm` by default:

- `ttft_overhead_p50_ms = target.ttft_p50_ms - direct_vllm.ttft_p50_ms`
- `latency_overhead_p50_ms = target.total_latency_p50_ms - direct_vllm.total_latency_p50_ms`

Compare percentiles over multiple repetitions instead of relying on one request.

## Logging Checklist

Some observability features cannot be proven from the client side. Use the logging checklist to record evidence from wrapper dashboards, databases, logs, Prometheus endpoints, OpenTelemetry collectors, or exported logs.

Examples include request IDs, prompt/response logging, redaction, token usage, latency logging, retry/fallback traces, virtual keys, and export integrations.

## Limitations

- TTFT is affected by vLLM queueing, GPU load, prompt length, and network.
- Wrapper overhead may be small compared to model generation time.
- Run multiple repetitions and compare percentiles, not one request.
- Logging and caching can change latency.
- Some logging capabilities require manual verification in wrapper dashboards.
- Some wrappers may buffer streaming chunks, affecting TTFT.
- Model quality is not compared because every target uses the same upstream model.
