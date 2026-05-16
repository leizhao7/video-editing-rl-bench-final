from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field


class RunRecord(BaseModel):
    run_id: str = Field(default_factory=lambda: uuid4().hex[:12])
    task_id: str
    agent: str
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    workspace: Path
    status: Literal["prepared", "running", "completed", "failed", "scored"] = "prepared"
    metadata: dict[str, Any] = Field(default_factory=dict)


class ScoreRecord(BaseModel):
    run_id: str
    task_id: str
    agent: str
    scores: dict[str, float]
    total: float
    suspected_reward_hacking: bool = False
    notes: list[str] = Field(default_factory=list)

