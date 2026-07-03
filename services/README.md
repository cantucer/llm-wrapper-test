# Wrapper Service Setup

The benchmark app does not install or start gateway services. Start each wrapper separately, test it with curl, then add it to `configs/targets.yaml`.

Use these files as local templates for:

- LiteLLM Proxy on `http://localhost:4000/v1`
- Bifrost on `http://localhost:8080/v1`
- Portkey Gateway on `http://localhost:8787/v1`
- Helicone AI Gateway on `http://localhost:8081/v1`
- LLM Gateway on `http://localhost:3000/v1`

Set `DIRECT_VLLM_BASE_URL`, `DIRECT_VLLM_API_KEY`, and wrapper-specific API key variables before running scripts.
