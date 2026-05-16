#!/usr/bin/env bash
set -euo pipefail

IMAGE_NAME="${1:-video-bench-agent:cpu}"
docker build -f docker/agent-cpu/Dockerfile -t "${IMAGE_NAME}" .

