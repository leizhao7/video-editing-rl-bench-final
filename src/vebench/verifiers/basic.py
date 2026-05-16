from __future__ import annotations

from pathlib import Path

from ..media.ffprobe import duration_seconds
from ..schema import ScoreRecord


def basic_submission_score(*, run_id: str, task_id: str, agent: str, workspace: Path) -> ScoreRecord:
    output = workspace / "submit" / "output.mp4"
    edit_json = workspace / "submit" / "edit_decision.json"
    run_history = workspace / "submit" / "run_history.md"
    agent_transcript = workspace / "submit" / "agent_transcript.md"

    scores = {
        "output_exists": 1.0 if output.exists() and output.stat().st_size > 0 else 0.0,
        "edit_decision_exists": 1.0 if edit_json.exists() and edit_json.stat().st_size > 0 else 0.0,
        "run_history_exists": 1.0 if run_history.exists() and run_history.stat().st_size >= 80 else 0.0,
        "agent_transcript_exists": 1.0
        if agent_transcript.exists() and agent_transcript.stat().st_size >= 80
        else 0.0,
        "run_history_transcript_score": 0.0,
        "playable_video": 0.0,
    }
    scores["run_history_transcript_score"] = (
        scores["run_history_exists"] + scores["agent_transcript_exists"]
    ) / 2.0
    notes: list[str] = []

    if scores["output_exists"]:
        try:
            scores["playable_video"] = 1.0 if duration_seconds(output) > 0 else 0.0
        except Exception as exc:  # noqa: BLE001
            notes.append(f"ffprobe failed: {exc}")

    total = sum(scores.values()) / len(scores)
    return ScoreRecord(
        run_id=run_id,
        task_id=task_id,
        agent=agent,
        scores=scores,
        total=total,
        suspected_reward_hacking=False,
        notes=notes,
    )
