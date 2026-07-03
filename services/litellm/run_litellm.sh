#!/usr/bin/env bash
set -euo pipefail

: "${DIRECT_VLLM_BASE_URL:?Set DIRECT_VLLM_BASE_URL}"
: "${DIRECT_VLLM_API_KEY:=dummy}"
: "${LITELLM_MASTER_KEY:=sk-litellm-test}"

litellm --config services/litellm/litellm_config.yaml --port 4000
