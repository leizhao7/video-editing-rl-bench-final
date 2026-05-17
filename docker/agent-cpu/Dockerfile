FROM python:3.11-slim-bookworm

ENV DEBIAN_FRONTEND=noninteractive \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    gnupg \
  && mkdir -p /etc/apt/keyrings \
  && curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key \
    | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg \
  && echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_20.x nodistro main" \
    > /etc/apt/sources.list.d/nodesource.list \
  && apt-get update && apt-get install -y --no-install-recommends \
    bash \
    build-essential \
    ffmpeg \
    git \
    jq \
    libgl1 \
    libglib2.0-0 \
    libsndfile1 \
    nodejs \
    pkg-config \
    poppler-utils \
    procps \
    tini \
  && rm -rf /var/lib/apt/lists/*

RUN node --version && npm --version \
  && npm install -g @openai/codex @anthropic-ai/claude-code @google/gemini-cli

WORKDIR /opt/vebench
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install -U pip setuptools wheel && pip install -e .

RUN mkdir -p /workspace /agent-home
ENV HOME=/agent-home
WORKDIR /workspace

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["bash"]
