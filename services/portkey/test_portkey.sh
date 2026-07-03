#!/usr/bin/env bash
set -euo pipefail

: "${DIRECT_VLLM_BASE_URL:?Set DIRECT_VLLM_BASE_URL}"
: "${PORTKEY_PROVIDER_API_KEY:=dummy}"

curl -X POST "http://localhost:8787/v1/chat/completions" \
  -H "Authorization: Bearer ${PORTKEY_PROVIDER_API_KEY}" \
  -H "Content-Type: application/json" \
  -H "x-portkey-provider: openai" \
  -H "x-portkey-custom-host: ${DIRECT_VLLM_BASE_URL}" \
  -d '{
    "model": "qwen3-6",
    "messages": [{"role": "user", "content": "Say OK"}],
    "stream": false
  }'
