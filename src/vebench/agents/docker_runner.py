from __future__ import annotations

import os
import subprocess
from pathlib import Path


def _env_flags(agent: str) -> list[str]:
    flags: list[str] = []
    if agent == "codex" and os.environ.get("OPENAI_API_KEY"):
        flags += ["-e", "OPENAI_API_KEY"]
    if agent == "claude" and os.environ.get("ANTHROPIC_API_KEY"):
        flags += ["-e", "ANTHROPIC_API_KEY"]
    return flags


def _agent_command(agent: str) -> str:
    if agent == "codex":
        return (
            "codex exec --sandbox workspace-write --ask-for-approval never "
            "\"$(cat prompt.md)\" 2>&1 | tee _logs/codex.log"
        )
    if agent == "claude":
        return (
            "claude -p --permission-mode bypassPermissions --output-format stream-json "
            "\"$(cat prompt.md)\" 2>&1 | tee _logs/claude.jsonl"
        )
    if agent == "shell-smoke":
        return (
            "ffmpeg -y -f lavfi -i color=c=black:s=320x180:d=1 "
            "-f lavfi -i anullsrc=channel_layout=stereo:sample_rate=44100 "
            "-shortest -c:v libx264 -pix_fmt yuv420p -c:a aac submit/output.mp4 "
            "&& printf '{\"operations\": [], \"tools_used\": [\"smoke\", \"ffmpeg\"]}\\n' "
            "> submit/edit_decision.json "
            "&& echo 'smoke submission created'"
        )
    raise ValueError(f"Unsupported docker agent: {agent}")


def run_in_docker(
    *,
    agent: str,
    workspace: Path,
    image: str,
    cpus: str = "8",
    memory: str = "16g",
    network: str = "bridge",
) -> int:
    workspace = workspace.resolve()
    cmd = [
        "docker",
        "run",
        "--rm",
        "--network",
        network,
        "--cpus",
        cpus,
        "--memory",
        memory,
        "-v",
        f"{workspace}:/workspace",
        "-w",
        "/workspace",
        *_env_flags(agent),
        image,
        "bash",
        "-lc",
        _agent_command(agent),
    ]
    completed = subprocess.run(cmd, check=False)
    return completed.returncode
