FROM python:3.11-slim-bookworm

ENV DEBIAN_FRONTEND=noninteractive \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    bash \
    build-essential \
    ca-certificates \
    curl \
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
    procps \
    tini \
  && rm -rf /var/lib/apt/lists/*

RUN npm install -g @openai/codex @anthropic-ai/claude-code

WORKDIR /opt/vebench
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install -U pip setuptools wheel && pip install -e .

RUN mkdir -p /workspace /agent-home
ENV HOME=/agent-home
WORKDIR /workspace

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["bash"]

