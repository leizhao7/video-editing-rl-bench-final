from __future__ import annotations

from pathlib import Path

from ..media.ffprobe import duration_seconds
from ..schema import ScoreRecord


def basic_submission_score(*, run_id: str, task_id: str, agent: str, workspace: Path) -> ScoreRecord:
    output = workspace / "submit" / "output.mp4"
    edit_json = workspace / "submit" / "edit_decision.json"

    scores = {
        "output_exists": 1.0 if output.exists() and output.stat().st_size > 0 else 0.0,
        "edit_decision_exists": 1.0 if edit_json.exists() and edit_json.stat().st_size > 0 else 0.0,
        "playable_video": 0.0,
    }
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

