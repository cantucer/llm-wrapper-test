#!/usr/bin/env bash
set -euo pipefail

docker run --rm \
  -p 8081:8080 \
  helicone/ai-gateway
