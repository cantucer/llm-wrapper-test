#!/usr/bin/env bash
set -euo pipefail

mkdir -p services/bifrost/data
docker run --rm \
  -p 8080:8080 \
  -v "$(pwd)/services/bifrost/data:/app/data" \
  maximhq/bifrost
