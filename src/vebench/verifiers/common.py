from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

try:
    from jsonschema import Draft202012Validator
except ModuleNotFoundError:  # pragma: no cover - dependency is installed in the benchmark env.
    Draft202012Validator = None


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def ramp_score(value: float, *, good: float, bad: float, lower_is_better: bool = True) -> float:
    if lower_is_better:
        if value <= good:
            return 1.0
        if value >= bad:
            return 0.0
        return 1.0 - (value - good) / (bad - good)
    if value >= good:
        return 1.0
    if value <= bad:
        return 0.0
    return (value - bad) / (good - bad)


def window_score(value: float, *, gate: tuple[float, float], target: tuple[float, float]) -> float:
    low_gate, high_gate = gate
    low_target, high_target = target
    if value < low_gate or value > high_gate:
        return 0.0
    if low_target <= value <= high_target:
        return 1.0
    if value < low_target:
        return (value - low_gate) / (low_target - low_gate)
    return (high_gate - value) / (high_gate - high_target)


def aspect_score(width: int, height: int, aspect: str, *, tolerance: float = 0.02) -> float:
    if width <= 0 or height <= 0:
        return 0.0
    observed = width / height
    target = 9 / 16 if aspect == "portrait_9_16" else 16 / 9
    error = abs(observed - target) / target
    if error <= tolerance:
        return 1.0
    if error >= tolerance * 4:
        return 0.0
    return 1.0 - (error - tolerance) / (tolerance * 3)


def interval_overlap(a: tuple[float, float], b: tuple[float, float]) -> float:
    return max(0.0, min(a[1], b[1]) - max(a[0], b[0]))


def total_overlap(ranges: list[tuple[float, float]], interval: tuple[float, float]) -> float:
    return sum(interval_overlap(rng, interval) for rng in ranges)


def load_json_if_exists(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def validate_json(path: Path, schema: dict[str, Any] | None = None) -> tuple[float, dict[str, Any], list[str]]:
    notes: list[str] = []
    if not path.exists() or path.stat().st_size == 0:
        return 0.0, {}, [f"missing JSON: {path.name}"]
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        return 0.0, {}, [f"invalid JSON: {exc}"]
    if schema and Draft202012Validator is not None:
        errors = sorted(Draft202012Validator(schema).iter_errors(data), key=lambda item: item.path)
        if errors:
            first = errors[0]
            notes.append(f"schema validation failed at {list(first.path)}: {first.message}")
            return 0.35, data, notes
    elif schema:
        missing = [key for key in schema.get("required", []) if key not in data]
        if missing:
            notes.append(f"schema validation degraded; missing required keys: {missing}")
            return 0.35, data, notes
    return 1.0, data, notes


def extract_source_ranges(edit: dict[str, Any]) -> list[tuple[float, float]]:
    ranges: list[tuple[float, float]] = []
    candidates: list[Any] = []
    for key in ["source_ranges", "kept_segments", "segments", "operations"]:
        value = edit.get(key)
        if isinstance(value, list):
            candidates.extend(value)
    for item in candidates:
        if not isinstance(item, dict):
            continue
        start = item.get("source_start", item.get("start", item.get("in")))
        end = item.get("source_end", item.get("end", item.get("out")))
        if isinstance(start, (int, float)) and isinstance(end, (int, float)) and end > start:
            ranges.append((float(start), float(end)))
    ranges.sort()
    return ranges


def extract_removed_ranges(edit: dict[str, Any]) -> list[tuple[float, float]]:
    ranges: list[tuple[float, float]] = []
    for key in ["removed_defects", "removed_damage_ranges", "removed_ranges"]:
        for item in edit.get(key, []) if isinstance(edit.get(key), list) else []:
            if not isinstance(item, dict):
                continue
            start = item.get("source_start", item.get("start"))
            end = item.get("source_end", item.get("end"))
            if isinstance(start, (int, float)) and isinstance(end, (int, float)) and end > start:
                ranges.append((float(start), float(end)))
    return ranges


def extract_local_shifts(edit: dict[str, Any]) -> list[dict[str, float]]:
    shifts: list[dict[str, float]] = []
    for key in ["local_audio_shifts_ms", "audio_shifts_ms", "audio_shifts"]:
        value = edit.get(key)
        if not isinstance(value, list):
            continue
        for item in value:
            if not isinstance(item, dict):
                continue
            start = item.get("source_start", item.get("start"))
            end = item.get("source_end", item.get("end"))
            shift = item.get("shift_ms", item.get("audio_shift_ms"))
            if all(isinstance(v, (int, float)) for v in [start, end, shift]) and end > start:
                shifts.append({"source_start": float(start), "source_end": float(end), "shift_ms": float(shift)})
    for item in edit.get("segments", []) if isinstance(edit.get("segments"), list) else []:
        if not isinstance(item, dict):
            continue
        shift = item.get("shift_ms", item.get("audio_shift_ms"))
        start = item.get("source_start")
        end = item.get("source_end")
        if all(isinstance(v, (int, float)) for v in [start, end, shift]) and end > start:
            shifts.append({"source_start": float(start), "source_end": float(end), "shift_ms": float(shift)})
    return shifts


def monotonicity_score(ranges: list[tuple[float, float]]) -> float:
    if len(ranges) < 2:
        return 0.5 if ranges else 0.0
    inversions = 0
    for prev, current in zip(ranges, ranges[1:]):
        if current[0] + 0.25 < prev[0]:
            inversions += 1
    return clamp01(1.0 - inversions / max(1, len(ranges) - 1))


def parse_srt(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    text = path.read_text(errors="replace")
    entries: list[dict[str, Any]] = []
    pattern = re.compile(
        r"(?P<idx>\d+)\s+"
        r"(?P<start>\d\d:\d\d:\d\d,\d\d\d)\s+-->\s+(?P<end>\d\d:\d\d:\d\d,\d\d\d)\s+"
        r"(?P<text>.*?)(?=\n\s*\d+\s+\d\d:\d\d:\d\d,\d\d\d|\Z)",
        re.S,
    )
    for match in pattern.finditer(text):
        entries.append(
            {
                "start": _srt_time(match.group("start")),
                "end": _srt_time(match.group("end")),
                "text": " ".join(match.group("text").strip().split()),
            }
        )
    return entries


def srt_text(entries: list[dict[str, Any]]) -> str:
    return " ".join(str(entry.get("text", "")) for entry in entries).lower()


def _srt_time(value: str) -> float:
    hh, mm, rest = value.split(":")
    ss, ms = rest.split(",")
    return int(hh) * 3600 + int(mm) * 60 + int(ss) + int(ms) / 1000.0
