#!/usr/bin/env bash
set -euo pipefail

: "${HELICONE_API_KEY:=dummy}"

curl -X POST "http://localhost:8081/v1/chat/completions" \
  -H "Authorization: Bearer ${HELICONE_API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen3-6",
    "messages": [{"role": "user", "content": "Say OK"}],
    "stream": false
  }'
