#!/usr/bin/env bash
set -euo pipefail

: "${BIFROST_API_KEY:=dummy}"

curl -X POST "http://localhost:8080/v1/chat/completions" \
  -H "Authorization: Bearer ${BIFROST_API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "vllm/qwen3-6",
    "messages": [{"role": "user", "content": "Say OK"}],
    "stream": false
  }'
