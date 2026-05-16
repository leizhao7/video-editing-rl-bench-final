#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root on the VPS." >&2
  exit 1
fi

export DEBIAN_FRONTEND=noninteractive

apt-get update
apt-get install -y ca-certificates curl gnupg lsb-release

apt-get install -y \
  build-essential \
  ffmpeg \
  git \
  jq \
  libgl1 \
  libglib2.0-0 \
  libsndfile1 \
  nodejs \
  npm \
  pkg-config \
  poppler-utils \
  python3.11 \
  python3.11-venv \
  rsync \
  unzip

if ! command -v docker >/dev/null 2>&1; then
  apt-get install -y docker.io
  systemctl enable --now docker
fi

mkdir -p /data/video-agent/{raw,tasks,submissions,cache,tmp,outputs,logs,models,docker,runs}

mkdir -p /etc/docker
cat >/etc/docker/daemon.json <<'EOF'
{
  "data-root": "/data/video-agent/docker",
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "100m",
    "max-file": "3"
  }
}
EOF
systemctl restart docker

cat >/etc/profile.d/video-agent.sh <<'EOF'
export VEBENCH_DATA_ROOT=/data/video-agent
export VIDEO_AGENT_HOME=/data/video-agent
export HF_HOME=/data/video-agent/cache/huggingface
export TORCH_HOME=/data/video-agent/cache/torch
export XDG_CACHE_HOME=/data/video-agent/cache
export TMPDIR=/data/video-agent/tmp
EOF
chmod 644 /etc/profile.d/video-agent.sh

echo "VPS bootstrap complete."
echo "Next:"
echo "  cd /bench/video-editing-rl-bench"
echo "  python3.11 -m venv .venv"
echo "  source .venv/bin/activate"
echo "  pip install -U pip"
echo "  pip install -e ."
