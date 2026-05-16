from __future__ import annotations

from .base import TaskDefinition
from .definitions import TASK_DEFINITIONS


def task_ids() -> list[str]:
    return sorted(TASK_DEFINITIONS)


def get_task_definition(task_id: str) -> TaskDefinition:
    try:
        return TASK_DEFINITIONS[task_id]()
    except KeyError as exc:
        known = ", ".join(task_ids())
        raise KeyError(f"Unknown task id {task_id!r}. Known tasks: {known}") from exc
