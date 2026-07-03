#!/usr/bin/env bash
set -euo pipefail

: "${LLM_GATEWAY_API_KEY:=dummy}"

curl -X POST "http://localhost:3000/v1/chat/completions" \
  -H "Authorization: Bearer ${LLM_GATEWAY_API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen3-6",
    "messages": [{"role": "user", "content": "Say OK"}],
    "stream": false
  }'
