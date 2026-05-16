from __future__ import annotations

import os
from pathlib import Path


def repo_root() -> Path:
    return Path.cwd()


def data_root() -> Path:
    return Path(os.environ.get("VEBENCH_DATA_ROOT", "/data/video-agent"))


def default_image() -> str:
    return os.environ.get("VEBENCH_AGENT_IMAGE", "video-bench-agent:cpu")


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path

