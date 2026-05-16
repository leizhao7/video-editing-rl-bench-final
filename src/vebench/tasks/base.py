from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


GeneratorKind = Literal["direct_source", "piecewise_av_corruption", "rough_interview"]
AspectKind = Literal["portrait_9_16", "landscape_16_9"]


@dataclass(frozen=True)
class TaskDefinition:
    task_id: str
    title: str
    source_worker: str
    generator_kind: GeneratorKind
    source_url: str
    clip_start_sec: float
    clip_end_sec: float
    prompt: str
    edit_decision_schema: dict[str, Any]
    ground_truth: dict[str, Any]
    verifier_config: dict[str, Any]

    @property
    def clip_duration_sec(self) -> float:
        return self.clip_end_sec - self.clip_start_sec
