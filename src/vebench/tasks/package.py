from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from ..config import ensure_dir
from ..fs import write_json
from ..media.ffmpeg import (
    concat_mp4,
    make_black_clip,
    make_freeze_clip,
    make_shifted_segment,
    transcode_clip,
)
from .base import TaskDefinition
from .registry import get_task_definition


def generate_task_package(
    *,
    task_id: str,
    out_dir: Path,
    source: Path | None = None,
    force: bool = False,
) -> Path:
    task = get_task_definition(task_id)
    task_root = out_dir / task.task_id
    public = task_root / "public"
    private = task_root / "private"
    materials = public / "materials"

    if force and task_root.exists():
        shutil.rmtree(task_root)
    ensure_dir(materials)
    ensure_dir(private)

    _write_common_files(task, public=public, private=private)

    if source is not None:
        if not source.exists():
            raise FileNotFoundError(f"Missing source media: {source}")
        if task.generator_kind == "direct_source":
            transcode_clip(
                source=source,
                output=materials / "source.mp4",
                start_sec=task.clip_start_sec,
                end_sec=task.clip_end_sec,
            )
        elif task.generator_kind == "piecewise_av_corruption":
            _generate_piecewise_av_source(task, source=source, public=public, private=private)
        elif task.generator_kind == "rough_interview":
            _generate_rough_interview_source(task, source=source, public=public, private=private)
        else:
            raise ValueError(f"Unsupported generator kind: {task.generator_kind}")

    return task_root


def _write_common_files(task: TaskDefinition, *, public: Path, private: Path) -> None:
    (public / "prompt.md").write_text(task.prompt.rstrip() + "\n")
    (public / "tools.md").write_text(
        "# Available Tools\n\n"
        "- ffmpeg / ffprobe for media probing, trimming, filtering, subtitles, and export.\n"
        "- Python 3.11 with numpy, scipy, OpenCV, MoviePy, PyAV, librosa, pydub, Pillow, scikit-image, pandas, jsonschema.\n"
        "- faster-whisper may be used for local transcription when installed.\n"
    )
    write_json(public / "edit_decision.schema.json", task.edit_decision_schema)
    write_json(
        public / "source_metadata.json",
        {
            "task_id": task.task_id,
            "source_worker": task.source_worker,
            "source_url_hidden_from_agent": True,
            "clip_start_sec": task.clip_start_sec,
            "clip_end_sec": task.clip_end_sec,
            "expected_public_material": "materials/source.mp4",
        },
    )
    submission_files = ["submit/output.mp4", "submit/edit_decision.json"]
    if task.task_id == "rough_interview_caption_cleanup":
        submission_files.insert(1, "submit/captions.srt")
    write_json(
        public / "output_specs.json",
        {
            "task_id": task.task_id,
            "duration_gate": task.verifier_config["duration_gate"],
            "duration_target": task.verifier_config["duration_target"],
            "aspect": task.verifier_config["aspect"],
            "resolution": task.verifier_config.get("resolution"),
            "submission_files": submission_files,
        },
    )
    write_json(private / "ground_truth.json", task.ground_truth)
    write_json(private / "verifier_config.json", task.verifier_config)

    if task.task_id == "piecewise_av_sync_repair":
        write_json(private / "corruption_recipe.json", task.ground_truth["corruption_recipe"])
        write_json(private / "required_spans.json", {"required_spans": task.ground_truth["required_spans"]})
    elif task.task_id == "rough_interview_caption_cleanup":
        write_json(private / "defect_map.json", task.ground_truth["defect_map"])
        write_json(private / "semantic_anchors.json", {"semantic_anchors": task.ground_truth["semantic_anchors"]})


def _generate_piecewise_av_source(task: TaskDefinition, *, source: Path, public: Path, private: Path) -> None:
    clean = private / "clean_reference.mp4"
    transcode_clip(
        source=source,
        output=clean,
        start_sec=task.clip_start_sec,
        end_sec=task.clip_end_sec,
        resolution=(1280, 720),
        fps=30,
    )
    recipe = task.ground_truth["corruption_recipe"]
    with tempfile.TemporaryDirectory(prefix="vebench_sync_") as tmp_name:
        tmp = Path(tmp_name)
        parts: list[Path] = []
        leader = tmp / "000_black_leader.mp4"
        make_black_clip(leader, recipe["black_leader_sec"])
        parts.append(leader)

        offsets = recipe["piecewise_audio_offsets"]
        freeze = recipe["freeze_splice"]
        boundaries: list[tuple[float, float, int]] = []
        for zone in offsets:
            start = float(zone["clean_start_sec"])
            end = float(zone["clean_end_sec"])
            delay = int(zone["audio_delay_ms"])
            freeze_time = float(freeze["clean_time_sec"])
            if start < freeze_time < end:
                boundaries.append((start, freeze_time, delay))
                boundaries.append((freeze_time, end, delay))
            else:
                boundaries.append((start, end, delay))

        part_index = 1
        inserted_freeze = False
        for start, end, delay in boundaries:
            if end > start:
                out = tmp / f"{part_index:03d}_content.mp4"
                make_shifted_segment(
                    source=clean,
                    output=out,
                    start_sec=start,
                    duration_sec=end - start,
                    audio_delay_ms=delay,
                )
                parts.append(out)
                part_index += 1
            if not inserted_freeze and abs(end - float(freeze["clean_time_sec"])) < 0.001:
                out = tmp / f"{part_index:03d}_freeze.mp4"
                make_freeze_clip(
                    source=clean,
                    source_time_sec=float(freeze["clean_time_sec"]),
                    output=out,
                    work_dir=tmp,
                    duration_sec=float(freeze["duration_sec"]),
                )
                parts.append(out)
                part_index += 1
                inserted_freeze = True

        tail = tmp / f"{part_index:03d}_black_tail.mp4"
        make_black_clip(tail, recipe["black_tail_sec"])
        parts.append(tail)
        concat_mp4(parts, public / "materials" / "source.mp4", work_dir=tmp)


def _generate_rough_interview_source(task: TaskDefinition, *, source: Path, public: Path, private: Path) -> None:
    clean = private / "clean_reference.mp4"
    transcode_clip(
        source=source,
        output=clean,
        start_sec=task.clip_start_sec,
        end_sec=task.clip_end_sec,
        resolution=(1280, 720),
        fps=30,
    )
    defect_map = task.ground_truth["defect_map"]
    events: list[tuple[float, str, dict[str, float]]] = []
    for event in defect_map["inserted_dead_air"]:
        events.append((float(event["clean_time_sec"]), "dead_air", event))
    for event in defect_map["repeated_phrase_loops"]:
        events.append((float(event["clean_start_sec"]), "repeat", event))
    events.sort(key=lambda item: item[0])

    with tempfile.TemporaryDirectory(prefix="vebench_interview_") as tmp_name:
        tmp = Path(tmp_name)
        parts: list[Path] = []
        cursor = 0.0
        part_index = 0
        for _, event_type, event in events:
            if event_type == "dead_air":
                t = float(event["clean_time_sec"])
                if t > cursor:
                    out = tmp / f"{part_index:03d}_content.mp4"
                    make_shifted_segment(source=clean, output=out, start_sec=cursor, duration_sec=t - cursor, audio_delay_ms=0)
                    parts.append(out)
                    part_index += 1
                    cursor = t
                freeze = tmp / f"{part_index:03d}_dead_air.mp4"
                make_freeze_clip(
                    source=clean,
                    source_time_sec=max(0.0, t - 0.05),
                    output=freeze,
                    work_dir=tmp,
                    duration_sec=float(event["duration_sec"]),
                )
                parts.append(freeze)
                part_index += 1
            elif event_type == "repeat":
                start = float(event["clean_start_sec"])
                end = float(event["clean_end_sec"])
                if start > cursor:
                    out = tmp / f"{part_index:03d}_content.mp4"
                    make_shifted_segment(source=clean, output=out, start_sec=cursor, duration_sec=start - cursor, audio_delay_ms=0)
                    parts.append(out)
                    part_index += 1
                phrase = tmp / f"{part_index:03d}_phrase.mp4"
                make_shifted_segment(source=clean, output=phrase, start_sec=start, duration_sec=end - start, audio_delay_ms=0)
                parts.append(phrase)
                part_index += 1
                for _ in range(max(0, int(event.get("repeat_count", 2)) - 1)):
                    repeat = tmp / f"{part_index:03d}_repeat.mp4"
                    make_shifted_segment(source=clean, output=repeat, start_sec=start, duration_sec=end - start, audio_delay_ms=0)
                    parts.append(repeat)
                    part_index += 1
                cursor = end

        if cursor < task.clip_duration_sec:
            out = tmp / f"{part_index:03d}_tail.mp4"
            make_shifted_segment(
                source=clean,
                output=out,
                start_sec=cursor,
                duration_sec=task.clip_duration_sec - cursor,
                audio_delay_ms=0,
            )
            parts.append(out)
        concat_mp4(parts, public / "materials" / "source.mp4", work_dir=tmp)
