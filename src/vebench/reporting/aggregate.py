from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


def aggregate_scores(*, runs_dir: Path, output: Path) -> Path:
    rows: list[dict[str, object]] = []
    for score_path in sorted(runs_dir.glob("*/score.json")):
        data = json.loads(score_path.read_text())
        row: dict[str, object] = {
            "run_id": data["run_id"],
            "task_id": data["task_id"],
            "task_type": data["task_id"],
            "agent": data["agent"],
            "total": data["total"],
            "suspected_reward_hacking": data.get("suspected_reward_hacking", False),
            "notes": "; ".join(data.get("notes", [])),
        }
        row.update(data.get("scores", {}))
        rows.append(row)

    output.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(output, sep="\t", index=False)
    return output

