from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


TASK_TYPES = {
    "piecewise_av_sync_repair": "av_sync_repair",
    "expert_pancake_vertical_short": "vertical_tutorial_extraction",
    "rough_interview_caption_cleanup": "interview_caption_cleanup",
}


def aggregate_scores(*, runs_dir: Path, output: Path) -> Path:
    rows: list[dict[str, object]] = []
    for score_path in sorted(runs_dir.glob("*/score.json")):
        data = json.loads(score_path.read_text())
        run_path = score_path.parent / "run.json"
        run_data = json.loads(run_path.read_text()) if run_path.exists() else {}
        metadata = run_data.get("metadata", {})
        scores = data.get("scores", {})
        row: dict[str, object] = {
            "task_id": data["task_id"],
            "task_type": TASK_TYPES.get(data["task_id"], data["task_id"]),
            "agent": data["agent"],
            "model": metadata.get("model", ""),
            "effort": metadata.get("effort", ""),
            "run_id": data["run_id"],
            "run_status": run_data.get("status", ""),
            "runner_returncode": metadata.get("returncode", ""),
            "total": data["total"],
            "suspected_reward_hacking": data.get("suspected_reward_hacking", False),
            "notes": "; ".join(data.get("notes", [])),
        }
        row.update(scores)
        rows.append(row)

    output.parent.mkdir(parents=True, exist_ok=True)
    leading_columns = [
        "task_id",
        "task_type",
        "agent",
        "model",
        "effort",
        "run_id",
        "run_status",
        "runner_returncode",
        "total",
        "suspected_reward_hacking",
    ]
    if rows:
        score_columns = sorted({key for row in rows for key in row if key not in {*leading_columns, "notes"}})
        columns = leading_columns + score_columns + ["notes"]
        df = pd.DataFrame(rows).reindex(columns=columns)
    else:
        df = pd.DataFrame(columns=leading_columns + ["notes"])
    df.to_csv(output, sep="\t", index=False)
    return output
