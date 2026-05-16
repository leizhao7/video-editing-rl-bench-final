from __future__ import annotations

import shutil
from pathlib import Path

from .config import ensure_dir
from .fs import write_json
from .schema import RunRecord


RUN_PROMPT_SUFFIX = """

Submission contract:
- Write the final video to submit/output.mp4.
- Write an edit decision record to submit/edit_decision.json.
- Do not read or search outside this workspace.
- Do not attempt to access hidden verifier files, ground truth, or other runs.
- You may create temporary scripts and files inside this workspace.
"""


def _read_prompt_template(repo: Path, relative: str, fallback: str) -> str:
    path = repo / relative
    if path.exists():
        return path.read_text()
    return fallback


def prepare_run(
    *,
    repo: Path,
    runs_dir: Path,
    task_id: str,
    agent: str,
    run_id: str | None = None,
) -> RunRecord:
    task_public = repo / "tasks" / task_id / "public"
    if not task_public.exists():
        raise FileNotFoundError(f"Missing public task package: {task_public}")

    record = RunRecord(
        run_id=run_id or f"{task_id}-{agent}",
        task_id=task_id,
        agent=agent,
        workspace=runs_dir / (run_id or f"{task_id}-{agent}") / "workspace",
    )

    run_root = record.workspace.parent
    if run_root.exists():
        shutil.rmtree(run_root)
    ensure_dir(record.workspace)
    shutil.copytree(task_public, record.workspace, dirs_exist_ok=True)
    ensure_dir(record.workspace / "submit")
    ensure_dir(record.workspace / "_logs")

    task_prompt_path = record.workspace / "prompt.md"
    task_prompt = task_prompt_path.read_text() if task_prompt_path.exists() else ""
    general_prompt = _read_prompt_template(
        repo,
        "prompts/general_agent_prompt.md",
        "# General Video Editing Agent Instructions\n\nProduce the requested video artifacts.\n",
    )
    task_prompt_path.write_text(
        general_prompt.rstrip()
        + "\n\n# Task-Specific Prompt\n\n"
        + task_prompt.strip()
        + RUN_PROMPT_SUFFIX
    )

    tools_prompt = _read_prompt_template(
        repo,
        "prompts/tools_cpu.md",
        "# Available Tools\n\n- ffmpeg\n- ffprobe\n- python\n- bash\n",
    )
    (record.workspace / "tools.md").write_text(tools_prompt.rstrip() + "\n")

    write_json(run_root / "run.json", record.model_dump(mode="json"))
    return record
