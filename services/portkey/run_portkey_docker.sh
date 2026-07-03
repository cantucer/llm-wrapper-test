#!/usr/bin/env bash
set -euo pipefail

docker run --rm \
  -p 8787:8787 \
  portkeyai/gateway:latest
