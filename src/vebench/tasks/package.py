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
    make_solid_clip,
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
    submission_files = [
        "submit/output.mp4",
        "submit/edit_decision.json",
        "submit/run_history.md",
        "submit/agent_transcript.md",
    ]
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
    (private / "hackability_analysis.md").write_text(_hackability_analysis_text(task).rstrip() + "\n")

    if task.task_id == "piecewise_av_sync_repair":
        write_json(private / "corruption_recipe.json", task.ground_truth["corruption_recipe"])
        write_json(private / "required_spans.json", {"required_spans": task.ground_truth["required_spans"]})
    elif task.task_id == "rough_interview_caption_cleanup":
        write_json(private / "defect_map.json", task.ground_truth["defect_map"])
        write_json(private / "semantic_anchors.json", {"semantic_anchors": task.ground_truth["semantic_anchors"]})


def _hackability_analysis_text(task: TaskDefinition) -> str:
    if task.task_id == "piecewise_av_sync_repair":
        return """# Hackability Analysis

## Main hacking risks

- Use one global audio shift instead of repairing the piecewise A/V offsets.
- Delete difficult sections instead of repairing local sync, visual artifacts, duplicate inserts, or dead air.
- Pad the output with black frames, frozen frames, silence, or unrelated filler to satisfy duration.
- Mute, clip, or replace audio while appearing to pass basic loudness checks.
- Claim repairs in `edit_decision.json` without producing the corresponding media changes.

## Anti-hacking defenses

- A/V sync is checked with private clean-reference anchors using both global and segmented residual scores.
- Required-span coverage, source-time monotonicity, and duration gates penalize over-trimming.
- Black-boundary, visual-artifact, freeze/dead-air, duplicate-insert, silence, clipping, and audio-quality checks detect common padding and deletion hacks.
- Documentation is scored only as a small provenance signal and cannot rescue bad media.
- Hard caps apply for missing output, invalid media, bad duration, low content preservation, low task score, remaining major artifacts, duplicate cleanup failure, or severe audio cleanup failure.

## Hackability classification

The sync and content-preservation dimensions are hard-to-hack because they depend on private clean-reference timing and private required spans. Audio and visual cleanup are hackable but bounded because local heuristics can be optimized narrowly, but severe silence, clipping, artifacts, and over-trimming are detectable. LLM judging, when enabled, is soft/vibes and used only as a minority or diagnostic signal.
"""
    if task.task_id == "expert_pancake_vertical_short":
        return """# Hackability Analysis

## Main hacking risks

- Submit any vertical video, generated footage, or unrelated source material.
- Use novice/blooper/reaction/end-card segments instead of the expert tutorial region.
- Delete most of the source to avoid negative material while losing recipe steps.
- Reorder clips into a plausible but non-causal montage.
- Fake vertical format with black bars, blurred padding, or a decorative landscape container.
- Add captions that are invisible, oversized, misplaced, generic, or unrelated to the visible action.
- Claim source ranges and captions in JSON without rendering the corresponding edit.

## Anti-hacking defenses

- Source authenticity and frame matching penalize external, generated, or unmatched material.
- Private allowed and negative source intervals score tutorial purity and penalize novice/blooper/end-card leakage.
- Private visual step intervals require pan prep, batter, bubble cue, flip, and plating coverage.
- Source-time monotonicity and step order checks penalize non-causal rearrangements.
- Vertical reframe checks detect fake portrait padding and weak crops.
- Caption visibility, step-caption completeness, caption/action alignment, and LLM caption rubrics bound caption hacks.
- Hard caps apply for missing output, wrong aspect, fake vertical format, heavy negative material, external material, weak step coverage, severe order failure, missing captions, and weak semantic captions.

## Hackability classification

Source-region selection, visual step coverage, temporal order, and source authenticity are hard-to-hack because they depend on private intervals and source-frame matching. Caption and crop quality are hackable but bounded because readability, placement, fake padding, ROI containment, and visual/source consistency checks catch the main hacks. The LLM judge is soft/vibes and used as a minority semantic layer.
"""
    if task.task_id == "rough_interview_caption_cleanup":
        return """# Hackability Analysis

## Main hacking risks

- Remove too much interview content to eliminate dead air while losing semantic anchors.
- Generate generic, copied, badly timed, oversized, or visually occluding captions.
- Submit a clean-looking output that no longer matches the original speech.
- Mute, replace, or over-normalize audio to satisfy simple loudness or silence checks.
- Use unrelated footage, synthetic narration, heavy overlays, or non-source material.
- Write plausible edit notes without preserving the required explanation.

## Anti-hacking defenses

- Private semantic anchors and ASR/token matching check that key explanation content remains.
- Inserted-pause cleanup is paired with duration, spoken-word density, source-fidelity, and semantic-preservation checks to prevent over-trimming.
- Caption verification combines SRT validity, ASR token F1, timing-aware token F1, caption-speech consistency, and LLM text/layout checks.
- Source matching and non-degenerate audio/video checks penalize unrelated footage, blank video, still frames, and source replacement.
- Caption layout caps penalize oversized subtitles, subject occlusion, or unreadable burned-in text.
- Hard caps apply for fatal media failures, low semantic recall, weak pause removal, missing captions, low source match, weak caption layout, low LLM quality, and obvious non-source/synthetic content.

## Hackability classification

Semantic anchor preservation and source fidelity are hard-to-hack because they depend on private transcript anchors and source matching. Speech cleanup, audio normalization, and caption timing are hackable but bounded because over-deletion, muting, clipping, and desynchronization are measurable. Caption visual layout and publishability remain soft/vibes, so LLM judging is a minority signal paired with caps.
"""
    return """# Hackability Analysis

This task uses private ground-truth criteria, media-integrity checks, and hard caps to reduce reward hacking. See `verifier_config.json` for concrete reward dimensions and cap thresholds.
"""


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
        flash = recipe.get("flash_insert")
        duplicate = recipe.get("duplicate_insert")
        gain_segments = recipe.get("audio_gain_segments", [])

        split_points = {0.0, float(task.clip_duration_sec)}
        for zone in offsets:
            split_points.add(float(zone["clean_start_sec"]))
            split_points.add(float(zone["clean_end_sec"]))
        if freeze:
            split_points.add(float(freeze["clean_time_sec"]))
        if flash:
            split_points.add(float(flash["clean_time_sec"]))
        if duplicate:
            split_points.add(float(duplicate["clean_start_sec"]))
            split_points.add(float(duplicate["clean_end_sec"]))
        for gain in gain_segments:
            split_points.add(float(gain["clean_start_sec"]))
            split_points.add(float(gain["clean_end_sec"]))

        points = sorted(point for point in split_points if 0.0 <= point <= float(task.clip_duration_sec))

        def offset_for(start: float) -> int:
            for zone in offsets:
                if float(zone["clean_start_sec"]) <= start < float(zone["clean_end_sec"]):
                    return int(zone["audio_delay_ms"])
            return 0

        def gain_for(start: float) -> float:
            for zone in gain_segments:
                if float(zone["clean_start_sec"]) <= start < float(zone["clean_end_sec"]):
                    return float(zone.get("gain_db", 0.0))
            return 0.0

        part_index = 1
        for start, end in zip(points, points[1:]):
            if end > start:
                out = tmp / f"{part_index:03d}_content.mp4"
                make_shifted_segment(
                    source=clean,
                    output=out,
                    start_sec=start,
                    duration_sec=end - start,
                    audio_delay_ms=offset_for(start),
                    audio_gain_db=gain_for(start),
                )
                parts.append(out)
                part_index += 1

            if flash and abs(end - float(flash["clean_time_sec"])) < 0.001:
                out = tmp / f"{part_index:03d}_flash.mp4"
                make_solid_clip(out, float(flash["duration_sec"]), color=str(flash.get("color", "white")))
                parts.append(out)
                part_index += 1

            if freeze and abs(end - float(freeze["clean_time_sec"])) < 0.001:
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

            if duplicate and abs(end - float(duplicate["clean_end_sec"])) < 0.001:
                for repeat_index in range(int(duplicate.get("repeat_count", 1))):
                    out = tmp / f"{part_index:03d}_duplicate_{repeat_index}.mp4"
                    dup_start = float(duplicate["clean_start_sec"])
                    dup_end = float(duplicate["clean_end_sec"])
                    make_shifted_segment(
                        source=clean,
                        output=out,
                        start_sec=dup_start,
                        duration_sec=dup_end - dup_start,
                        audio_delay_ms=offset_for(dup_start),
                        audio_gain_db=gain_for(dup_start),
                    )
                    parts.append(out)
                    part_index += 1

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
        timeline: list[dict[str, float | str]] = []
        defect_public_intervals: list[dict[str, float | str]] = []
        cursor = 0.0
        public_cursor = 0.0
        part_index = 0
        for _, event_type, event in events:
            if event_type == "dead_air":
                t = float(event["clean_time_sec"])
                if t > cursor:
                    out = tmp / f"{part_index:03d}_content.mp4"
                    make_shifted_segment(source=clean, output=out, start_sec=cursor, duration_sec=t - cursor, audio_delay_ms=0)
                    parts.append(out)
                    timeline.append(
                        {
                            "kind": "content",
                            "public_start": public_cursor,
                            "public_end": public_cursor + (t - cursor),
                            "clean_start": cursor,
                            "clean_end": t,
                        }
                    )
                    public_cursor += t - cursor
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
                duration = float(event["duration_sec"])
                timeline.append(
                    {
                        "kind": "inserted_dead_air",
                        "public_start": public_cursor,
                        "public_end": public_cursor + duration,
                        "clean_start": t,
                        "clean_end": t,
                    }
                )
                defect_public_intervals.append(
                    {
                        "kind": "inserted_dead_air",
                        "public_start": public_cursor,
                        "public_end": public_cursor + duration,
                        "clean_time_sec": t,
                    }
                )
                public_cursor += duration
                part_index += 1
            elif event_type == "repeat":
                start = float(event["clean_start_sec"])
                end = float(event["clean_end_sec"])
                if start > cursor:
                    out = tmp / f"{part_index:03d}_content.mp4"
                    make_shifted_segment(source=clean, output=out, start_sec=cursor, duration_sec=start - cursor, audio_delay_ms=0)
                    parts.append(out)
                    timeline.append(
                        {
                            "kind": "content",
                            "public_start": public_cursor,
                            "public_end": public_cursor + (start - cursor),
                            "clean_start": cursor,
                            "clean_end": start,
                        }
                    )
                    public_cursor += start - cursor
                    part_index += 1
                phrase = tmp / f"{part_index:03d}_phrase.mp4"
                make_shifted_segment(source=clean, output=phrase, start_sec=start, duration_sec=end - start, audio_delay_ms=0)
                parts.append(phrase)
                timeline.append(
                    {
                        "kind": "content",
                        "public_start": public_cursor,
                        "public_end": public_cursor + (end - start),
                        "clean_start": start,
                        "clean_end": end,
                    }
                )
                public_cursor += end - start
                part_index += 1
                for _ in range(max(0, int(event.get("repeat_count", 2)) - 1)):
                    repeat = tmp / f"{part_index:03d}_repeat.mp4"
                    make_shifted_segment(source=clean, output=repeat, start_sec=start, duration_sec=end - start, audio_delay_ms=0)
                    parts.append(repeat)
                    timeline.append(
                        {
                            "kind": "repeated_phrase_loop",
                            "public_start": public_cursor,
                            "public_end": public_cursor + (end - start),
                            "clean_start": start,
                            "clean_end": end,
                        }
                    )
                    defect_public_intervals.append(
                        {
                            "kind": "repeated_phrase_loop",
                            "public_start": public_cursor,
                            "public_end": public_cursor + (end - start),
                            "clean_start": start,
                            "clean_end": end,
                        }
                    )
                    public_cursor += end - start
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
            timeline.append(
                {
                    "kind": "content",
                    "public_start": public_cursor,
                    "public_end": public_cursor + (task.clip_duration_sec - cursor),
                    "clean_start": cursor,
                    "clean_end": task.clip_duration_sec,
                }
            )
        concat_mp4(parts, public / "materials" / "source.mp4", work_dir=tmp)
    write_json(private / "public_timeline.json", {"segments": timeline, "defect_public_intervals": defect_public_intervals})
