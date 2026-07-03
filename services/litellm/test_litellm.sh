#!/usr/bin/env bash
set -euo pipefail

: "${LITELLM_MASTER_KEY:=sk-litellm-test}"

curl -X POST "http://localhost:4000/v1/chat/completions" \
  -H "Authorization: Bearer ${LITELLM_MASTER_KEY}" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen3-6",
    "messages": [{"role": "user", "content": "Say OK"}],
    "stream": false
  }'
