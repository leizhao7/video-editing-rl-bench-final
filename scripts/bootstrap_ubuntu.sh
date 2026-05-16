#!/usr/bin/env bash
set -euo pipefail

sudo apt-get update
sudo apt-get install -y \
  ffmpeg \
  python3.11 \
  python3.11-venv \
  python3-pip \
  git \
  build-essential \
  pkg-config \
  libsndfile1 \
  libgl1 \
  libglib2.0-0 \
  jq

echo "Bootstrap complete. Create a venv with:"
echo "python3.11 -m venv .venv && source .venv/bin/activate && pip install -U pip && pip install -e ."

