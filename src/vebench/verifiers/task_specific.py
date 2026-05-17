from __future__ import annotations

from pathlib import Path
from typing import Any
import re

import numpy as np

from ..media.audio import audio_quality_score, audio_stats, read_audio_mono
from ..media.captions import burned_caption_visibility_score, caption_layout_occlusion_score
from ..media.ffprobe import probe
from ..media.matching import (
    match_video_timeline,
    matched_fraction,
    seconds_in_intervals,
    sync_residual_matches,
    timeline_diversity,
    timeline_monotonicity,
)
from ..media.roi import roi_visibility_score
from ..media.transcribe import transcribe_video
from ..media.video import video_integrity_score, video_stats
from ..schema import ScoreRecord
from ..tasks.registry import get_task_definition
from .basic import basic_submission_score
from .common import (
    aspect_score,
    clamp01,
    extract_removed_ranges,
    extract_source_ranges,
    interval_overlap,
    load_json_if_exists,
    monotonicity_score,
    parse_srt,
    ramp_score,
    srt_text,
    total_overlap,
    validate_json,
    window_score,
)
from .llm_judge import maybe_run_llm_judge


def score_task_submission(
    *,
    run_id: str,
    task_id: str,
    agent: str,
    workspace: Path,
    repo: Path,
    llm_judge: bool = False,
    llm_model: str | None = None,
) -> ScoreRecord:
    try:
        task = get_task_definition(task_id)
    except KeyError:
        return basic_submission_score(run_id=run_id, task_id=task_id, agent=agent, workspace=workspace)

    private = repo / "tasks" / task_id / "private"
    ground_truth = load_json_if_exists(private / "ground_truth.json") or task.ground_truth
    config = load_json_if_exists(private / "verifier_config.json") or task.verifier_config
    schema = load_json_if_exists(workspace / "edit_decision.schema.json") or task.edit_decision_schema

    if task_id == "expert_pancake_vertical_short":
        return _score_pancake(run_id, task_id, agent, workspace, repo, ground_truth, config, schema, llm_judge, llm_model)
    if task_id == "piecewise_av_sync_repair":
        return _score_piecewise_sync(run_id, task_id, agent, workspace, repo, ground_truth, config, schema, llm_judge, llm_model)
    if task_id == "rough_interview_caption_cleanup":
        return _score_interview(run_id, task_id, agent, workspace, repo, ground_truth, config, schema, llm_judge, llm_model)
    return basic_submission_score(run_id=run_id, task_id=task_id, agent=agent, workspace=workspace)


def _media_context(workspace: Path, config: dict[str, Any]) -> tuple[dict[str, float], dict[str, Any], list[str], bool]:
    notes: list[str] = []
    output = workspace / "submit" / "output.mp4"
    source = workspace / "materials" / "source.mp4"
    context: dict[str, Any] = {
        "output_path": output,
        "source_path": source,
    }
    scores: dict[str, float] = {
        "gate_source_material_exists": 1.0 if source.exists() and source.stat().st_size > 0 else 0.0,
        "gate_output_exists": 1.0 if output.exists() and output.stat().st_size > 0 else 0.0,
        "gate_ffprobe_readable": 0.0,
        "gate_has_audio_video": 0.0,
        "gate_duration_valid": 0.0,
        "gate_aspect_valid": 0.0,
        "gate_non_degenerate_video": 0.0,
        "gate_non_degenerate_audio": 0.0,
    }
    scores.update(_history_artifact_scores(workspace))
    if scores["run_history_transcript_score"] < 1.0:
        notes.append("missing or too-small submit/run_history.md or submit/agent_transcript.md")
    fatal = False
    if not scores["gate_source_material_exists"]:
        notes.append("missing materials/source.mp4; task package is metadata-only or incomplete")
        fatal = True
    if not scores["gate_output_exists"]:
        return scores, context, [*notes, "missing submit/output.mp4"], True

    try:
        info = probe(output)
        context["probe"] = info
        scores["gate_ffprobe_readable"] = 1.0
    except Exception as exc:  # noqa: BLE001
        return scores, context, [f"ffprobe failed: {exc}"], True

    streams = info.get("streams", [])
    video_stream = next((stream for stream in streams if stream.get("codec_type") == "video"), None)
    audio_stream = next((stream for stream in streams if stream.get("codec_type") == "audio"), None)
    context["video_stream"] = video_stream
    context["audio_stream"] = audio_stream
    if video_stream and audio_stream:
        scores["gate_has_audio_video"] = 1.0
    else:
        notes.append("missing video or audio stream")
        fatal = True

    duration = float(info.get("format", {}).get("duration", 0.0))
    context["duration"] = duration
    gate = tuple(float(x) for x in config["duration_gate"])
    target = tuple(float(x) for x in config["duration_target"])
    scores["duration_target_score"] = window_score(duration, gate=gate, target=target)
    if gate[0] <= duration <= gate[1]:
        scores["gate_duration_valid"] = 1.0
    else:
        notes.append(f"duration {duration:.2f}s outside gate {gate}")
        fatal = True

    if video_stream:
        width = int(video_stream.get("width", 0))
        height = int(video_stream.get("height", 0))
        context["width"] = width
        context["height"] = height
        scores["aspect_score"] = aspect_score(width, height, config["aspect"])
        if scores["aspect_score"] >= 0.8:
            scores["gate_aspect_valid"] = 1.0
        else:
            notes.append(f"wrong aspect/resolution: {width}x{height}")
            fatal = True
        expected = config.get("resolution")
        if expected:
            scores["resolution_score"] = 1.0 if [width, height] == list(expected) else aspect_score(width, height, config["aspect"])
        else:
            min_height = int(config.get("min_height", 0))
            scores["resolution_score"] = 1.0 if height >= min_height else clamp01(height / max(1, min_height))
        vcodec = str(video_stream.get("codec_name", "")).lower()
        scores["video_codec_score"] = 1.0 if vcodec in {"h264", "avc1"} else 0.5

    if audio_stream:
        acodec = str(audio_stream.get("codec_name", "")).lower()
        scores["audio_codec_score"] = 1.0 if acodec in {"aac", "mp4a"} else 0.5

    try:
        vstats = video_stats(output)
        context["video_stats"] = vstats
        scores["video_integrity"] = video_integrity_score(vstats)
        if vstats.get("black_frame_ratio", 1.0) < 0.35 and vstats.get("max_frozen_run_sec", 999.0) < 8.0:
            scores["gate_non_degenerate_video"] = 1.0
        else:
            notes.append("degenerate video: too black or frozen")
            fatal = True
    except Exception as exc:  # noqa: BLE001
        notes.append(f"video stats unavailable: {exc}")
        scores["video_integrity"] = 0.5
        scores["gate_non_degenerate_video"] = 1.0

    try:
        astats = audio_stats(output)
        context["audio_stats"] = astats
        scores["audio_quality"] = audio_quality_score(astats)
        if astats.get("rms_dbfs", -120.0) > -55.0 and astats.get("clipping_fraction", 1.0) < 0.02:
            scores["gate_non_degenerate_audio"] = 1.0
        else:
            notes.append("degenerate audio: silent or clipped")
            fatal = True
    except Exception as exc:  # noqa: BLE001
        notes.append(f"audio stats unavailable: {exc}")
        scores["audio_quality"] = 0.5
        scores["gate_non_degenerate_audio"] = 1.0

    return scores, context, notes, fatal


def _score_pancake(
    run_id: str,
    task_id: str,
    agent: str,
    workspace: Path,
    repo: Path,
    ground_truth: dict[str, Any],
    config: dict[str, Any],
    schema: dict[str, Any],
    llm_judge: bool,
    llm_model: str | None,
) -> ScoreRecord:
    scores, context, notes, fatal = _media_context(workspace, config)
    edit_score, edit, edit_notes = validate_json(workspace / "submit" / "edit_decision.json", schema)
    notes.extend(edit_notes)
    scores["edit_decision_schema"] = edit_score

    output = Path(context["output_path"])
    source = Path(context["source_path"])
    matches = []
    if output.exists() and source.exists():
        matches = match_video_timeline(output=output, source=source, output_fps=1.0, source_fps=1.0, threshold=0.55)
    if not matches:
        notes.append("visual source matching unavailable or found no confident matches")
    output_duration = max(1.0, float(context.get("duration", 0.0)))
    source_match_fraction = matched_fraction(matches, output_duration=float(context.get("duration", 0.0)), sample_step_sec=1.0)
    diversity = timeline_diversity(matches)
    source_monotonicity = timeline_monotonicity(matches)
    scores["source_match_fraction"] = source_match_fraction
    scores["source_timeline_diversity"] = float(diversity)
    scores["source_time_monotonicity"] = source_monotonicity
    scores["r_source_authenticity"] = clamp01(
        0.75 * source_match_fraction
        + 0.15 * min(1.0, diversity / 4.0)
        + 0.10 * source_monotonicity
    )

    visual_step_scores: list[float] = []
    first_hits: list[float] = []
    caption_text = _caption_text(edit)
    caption_keyword_coverage, caption_order_score = _pancake_step_caption_scores(
        steps=ground_truth["required_steps"],
        caption_text=caption_text,
        scores=scores,
    )
    for step in ground_truth["required_steps"]:
        step_id = re.sub(r"[^a-zA-Z0-9_]+", "_", str(step.get("id", "step"))).strip("_")
        interval = tuple(float(x) for x in step["interval"])
        interval_duration = max(0.0, interval[1] - interval[0])
        covered = seconds_in_intervals(matches, [interval], sample_step_sec=1.0)
        good_coverage = min(4.0, max(2.5, interval_duration * 0.18))
        visual = ramp_score(covered, good=good_coverage, bad=0.0, lower_is_better=False)
        visual_step_scores.append(visual)
        scores[f"pancake_visual_step_{step_id}_covered_sec"] = covered
        scores[f"pancake_visual_step_{step_id}_score"] = visual
        hits = [match.source_time for match in matches if interval[0] <= match.source_time <= interval[1]]
        if hits:
            first_hits.append(min(hits))

    if len(first_hits) >= 4 and first_hits == sorted(first_hits):
        visual_order_score = 1.0
    elif len(first_hits) >= 3:
        visual_order_score = 0.7
    elif first_hits:
        visual_order_score = 0.35
    else:
        visual_order_score = 0.0
    visual_step_mean = sum(visual_step_scores) / max(1, len(visual_step_scores))
    visual_step_min = min(visual_step_scores) if visual_step_scores else 0.0
    scores["pancake_visual_step_mean"] = visual_step_mean
    scores["pancake_visual_step_min"] = visual_step_min
    scores["pancake_visual_step_order_score"] = visual_order_score
    scores["r_visual_step_completeness"] = clamp01(
        0.70 * visual_step_mean
        + 0.20 * visual_step_min
        + 0.10 * min(1.0, diversity / 5.0)
    )
    scores["r_temporal_order"] = clamp01(
        0.60 * source_monotonicity
        + 0.25 * visual_order_score
        + 0.15 * caption_order_score
    )

    negative_leak = 0.0
    for item in ground_truth["negative_intervals"]:
        negative_leak += seconds_in_intervals(matches, [tuple(float(x) for x in item["interval"])], sample_step_sec=1.0)
    negative_leak_ratio = clamp01(negative_leak / output_duration)
    allowed_intervals = [
        tuple(float(x) for x in item["interval"])
        for item in ground_truth.get("allowed_tutorial_intervals", [])
    ]
    if not allowed_intervals and ground_truth.get("required_steps"):
        step_intervals = [tuple(float(x) for x in step["interval"]) for step in ground_truth["required_steps"]]
        allowed_intervals = [(max(0.0, min(start for start, _end in step_intervals) - 10.0), max(end for _start, end in step_intervals))]
    off_tutorial_leak = _seconds_outside_intervals(matches, allowed_intervals, sample_step_sec=1.0) if allowed_intervals else negative_leak
    off_tutorial_leak_ratio = clamp01(off_tutorial_leak / output_duration)
    scores["negative_leak_seconds"] = negative_leak
    scores["negative_leak_ratio"] = negative_leak_ratio
    scores["off_tutorial_leak_seconds"] = off_tutorial_leak
    scores["off_tutorial_leak_ratio"] = off_tutorial_leak_ratio
    scores["tutorial_impurity_ratio"] = max(negative_leak_ratio, off_tutorial_leak_ratio)
    scores["r_tutorial_segment_purity"] = ramp_score(scores["tutorial_impurity_ratio"], good=0.05, bad=0.20, lower_is_better=True)

    caption_items = _caption_items(edit)
    caption_count = len(caption_items)
    caption_count_score = min(1.0, caption_count / 5.0)
    cue_times = _caption_cue_times(edit)
    caption_timing_metadata_score = min(1.0, len(cue_times) / max(1.0, float(min(5, max(1, caption_count)))))
    caption_visibility = burned_caption_visibility_score(output, cue_times)
    layout_score, layout_details = caption_layout_occlusion_score(output, cue_times)
    scores.update(layout_details)
    visual_caption_presence = max(
        caption_visibility,
        float(layout_details.get("caption_detected_frame_ratio", 0.0)),
    )
    caption_presence_score = max(caption_count_score, visual_caption_presence)
    caption_timing_score = max(caption_timing_metadata_score, 0.75 * visual_caption_presence)
    scores["caption_count"] = float(caption_count)
    scores["caption_count_score"] = caption_count_score
    scores["caption_visibility"] = caption_visibility
    scores["caption_visual_presence"] = visual_caption_presence
    scores["caption_timing_metadata_score"] = caption_timing_metadata_score
    scores["caption_text_metadata_available"] = 1.0 if caption_text.strip() else 0.0
    scores["r_caption_technical_quality"] = clamp01(
        0.24 * caption_presence_score
        + 0.30 * caption_visibility
        + 0.31 * layout_score
        + 0.15 * caption_timing_score
    )
    text_step_caption_score = clamp01(
        0.65 * caption_keyword_coverage
        + 0.20 * caption_count_score
        + 0.15 * caption_order_score
    )
    visual_caption_fallback = 0.45 * visual_caption_presence
    scores["r_step_caption_completeness"] = max(text_step_caption_score, visual_caption_fallback)
    text_caption_alignment = _pancake_caption_visual_alignment_score(
        caption_items=caption_items,
        matches=matches,
        steps=ground_truth["required_steps"],
        scores=scores,
    )
    visual_alignment_fallback = 0.45 * visual_caption_presence * scores["r_visual_step_completeness"]
    scores["r_caption_visual_alignment"] = max(text_caption_alignment, visual_alignment_fallback)

    border_score = 1.0 - float(context.get("video_stats", {}).get("border_black_fraction", 0.0))
    vertical_padding_score, padding_details = _pancake_vertical_padding_score(output)
    scores.update(padding_details)
    roi_annotations = load_json_if_exists(repo / "tasks" / task_id / "private" / "roi_keyframes.json")
    if roi_annotations:
        roi_score, roi_details = roi_visibility_score(
            source=source,
            output=output,
            matches=matches,
            roi_annotations=roi_annotations,
        )
        scores.update(roi_details)
    else:
        roi_score = min(scores.get("video_integrity", 0.0), border_score)
        notes.append("private roi_keyframes.json not found; using visual integrity/border fallback for ROI containment")
    scores["roi_containment_score"] = roi_score
    scores["r_no_fake_vertical_padding"] = vertical_padding_score
    scores["r_true_vertical_reframe"] = clamp01(
        0.20 * scores.get("aspect_score", 0.0)
        + 0.35 * vertical_padding_score
        + 0.20 * roi_score
        + 0.15 * border_score
        + 0.10 * scores.get("resolution_score", 0.0)
    )

    scores["r_format"] = _format_score(scores)
    scores["r_audio_quality"] = scores.get("audio_quality", 0.0)
    scores["r_video_quality"] = scores.get("video_integrity", 0.0)
    source_range_consistency = _edit_media_consistency_score(extract_source_ranges(edit), matches)
    scores["edit_media_consistency"] = source_range_consistency
    scores["r_provenance_and_logs"] = clamp01(
        0.45 * edit_score
        + 0.30 * source_range_consistency
        + 0.25 * scores.get("run_history_transcript_score", 0.0)
    )

    scores["hard_1_format_duration"] = scores["r_format"]
    scores["hard_2_source_authenticity_timeline"] = scores["r_source_authenticity"]
    scores["hard_3_expert_step_coverage_order"] = clamp01(
        0.45 * scores["r_visual_step_completeness"]
        + 0.30 * scores["r_temporal_order"]
        + 0.25 * scores["r_step_caption_completeness"]
    )
    scores["hard_4_negative_material_suppression"] = scores["r_tutorial_segment_purity"]
    scores["hard_5_vertical_roi_caption"] = clamp01(
        0.50 * scores["r_true_vertical_reframe"]
        + 0.30 * scores["r_caption_technical_quality"]
        + 0.20 * scores["r_caption_visual_alignment"]
    )
    scores["hard_6_audio_quality_cut_smoothness"] = scores["r_audio_quality"]
    scores["metadata"] = scores["r_provenance_and_logs"]

    general_weights = config.get(
        "general_weights",
        {
            "r_format": 0.30,
            "r_audio_quality": 0.20,
            "r_video_quality": 0.20,
            "r_source_authenticity": 0.15,
            "r_provenance_and_logs": 0.15,
        },
    )
    task_weights = config.get(
        "task_weights",
        {
            "r_tutorial_segment_purity": 0.25,
            "r_temporal_order": 0.20,
            "r_visual_step_completeness": 0.20,
            "r_caption_visual_alignment": 0.15,
            "r_step_caption_completeness": 0.10,
            "r_true_vertical_reframe": 0.10,
        },
    )
    scores["r_general"] = _weighted_score(scores, general_weights)
    scores["r_task"] = _weighted_score(scores, task_weights)
    hard_total = clamp01(
        float(config.get("general_weight", 0.20)) * scores["r_general"]
        + float(config.get("task_weight", 0.80)) * scores["r_task"]
    )
    scores["r_hard"] = hard_total
    scores["r_llm"] = 0.0
    total = hard_total

    if llm_judge:
        llm_scores, llm_notes, _raw = maybe_run_llm_judge(
            task_id=task_id,
            workspace=workspace,
            hard_scores=scores,
            edit_decision=edit,
            enabled=True,
            model=llm_model,
        )
        scores.update(llm_scores)
        notes.extend(llm_notes)
        if scores.get("llm_judge_available", 0.0) >= 1.0:
            scores["r_llm"] = scores.get("llm_overall", 0.0)
            llm_weight = float(config.get("llm_weight", 0.15))
            total = clamp01((1.0 - llm_weight) * hard_total + llm_weight * scores["r_llm"])
        else:
            scores["pancake_requested_llm_missing_cap"] = 0.75
            total = min(total, 0.75)
            notes.append("pancake LLM judge was requested but unavailable; semantic caption/alignment checks are partially capped.")

    scores["r_final_before_caps"] = total
    total, cap_notes = _apply_pancake_hard_caps(scores=scores, total=total, caps=config.get("hard_caps", {}), fatal=fatal)
    notes.extend(cap_notes)
    scores["r_final_after_caps"] = total
    return ScoreRecord(run_id=run_id, task_id=task_id, agent=agent, scores=scores, total=clamp01(total), notes=_verifier_notes(notes))


def _pancake_step_caption_scores(
    *,
    steps: list[dict[str, Any]],
    caption_text: str,
    scores: dict[str, float],
) -> tuple[float, float]:
    if not steps:
        return 0.0, 0.0
    hits = 0
    positions: list[int] = []
    for step in steps:
        step_id = re.sub(r"[^a-zA-Z0-9_]+", "_", str(step.get("id", "step"))).strip("_")
        keywords = _pancake_step_keywords(step)
        matched_positions = [caption_text.find(keyword) for keyword in keywords if keyword and caption_text.find(keyword) >= 0]
        step_hit = 1.0 if matched_positions else 0.0
        scores[f"pancake_caption_step_{step_id}_hit"] = step_hit
        if matched_positions:
            hits += 1
            positions.append(min(matched_positions))
    coverage = hits / len(steps)
    if len(positions) >= 4 and positions == sorted(positions):
        order = 1.0
    elif len(positions) >= 3:
        order = 0.7
    elif positions:
        order = 0.35
    else:
        order = 0.0
    scores["caption_step_keyword_coverage"] = coverage
    scores["caption_step_keyword_order"] = order
    return clamp01(coverage), clamp01(order)


def _pancake_step_keywords(step: dict[str, Any]) -> list[str]:
    raw = [str(value).lower() for value in step.get("keywords", [])]
    raw.extend(_tokens(str(step.get("label", "")).lower()))
    kept: list[str] = []
    for keyword in raw:
        cleaned = re.sub(r"[^a-z0-9']+", " ", keyword).strip().lower()
        if len(cleaned) < 3:
            continue
        if cleaned not in kept:
            kept.append(cleaned)
    return kept


def _caption_items(edit: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    captions = edit.get("captions")
    if not isinstance(captions, list):
        return items
    for item in captions:
        if isinstance(item, dict):
            text = str(item.get("text", item.get("caption", "")))
            start = item.get("start", item.get("output_start"))
            end = item.get("end", item.get("output_end"))
            parsed: dict[str, Any] = {"text": text.lower()}
            if isinstance(start, (int, float)):
                parsed["start"] = float(start)
            if isinstance(end, (int, float)):
                parsed["end"] = float(end)
            items.append(parsed)
        else:
            items.append({"text": str(item).lower()})
    return items


def _pancake_caption_visual_alignment_score(
    *,
    caption_items: list[dict[str, Any]],
    matches: list[Any],
    steps: list[dict[str, Any]],
    scores: dict[str, float],
) -> float:
    if not caption_items or not matches or not steps:
        scores["caption_visual_alignment_checked_steps"] = 0.0
        return 0.0
    step_scores: list[float] = []
    checked = 0
    for step in steps:
        step_id = re.sub(r"[^a-zA-Z0-9_]+", "_", str(step.get("id", "step"))).strip("_")
        keywords = _pancake_step_keywords(step)
        interval = tuple(float(x) for x in step["interval"])
        candidates = [
            item
            for item in caption_items
            if any(keyword in str(item.get("text", "")) for keyword in keywords)
        ]
        if not candidates:
            scores[f"caption_visual_alignment_{step_id}"] = 0.0
            step_scores.append(0.0)
            continue
        checked += 1
        aligned = 0.0
        for item in candidates:
            if "start" not in item:
                continue
            midpoint = float(item["start"])
            if "end" in item and float(item["end"]) > midpoint:
                midpoint = (midpoint + float(item["end"])) / 2.0
            source_time = _source_time_at_output_time(matches, output_time=midpoint)
            if source_time is None:
                continue
            if interval[0] - 3.0 <= source_time <= interval[1] + 3.0:
                aligned = 1.0
                break
        if aligned <= 0.0:
            aligned = 0.30
        scores[f"caption_visual_alignment_{step_id}"] = aligned
        step_scores.append(aligned)
    scores["caption_visual_alignment_checked_steps"] = float(checked)
    return clamp01(sum(step_scores) / max(1, len(step_scores)))


def _source_time_at_output_time(matches: list[Any], *, output_time: float) -> float | None:
    if not matches:
        return None
    nearest = min(matches, key=lambda item: abs(float(item.output_time) - output_time))
    if abs(float(nearest.output_time) - output_time) <= 3.0:
        return float(nearest.source_time)
    before = [match for match in matches if float(match.output_time) <= output_time]
    after = [match for match in matches if float(match.output_time) >= output_time]
    if before and after:
        left = max(before, key=lambda item: float(item.output_time))
        right = min(after, key=lambda item: float(item.output_time))
        left_output = float(left.output_time)
        right_output = float(right.output_time)
        if right_output <= left_output + 1e-6:
            return float(left.source_time)
        ratio = (output_time - left_output) / (right_output - left_output)
        return float(left.source_time) + ratio * (float(right.source_time) - float(left.source_time))
    return None


def _seconds_outside_intervals(matches: list[Any], intervals: list[tuple[float, float]], *, sample_step_sec: float) -> float:
    if not intervals:
        return 0.0
    total = 0.0
    for match in matches:
        source_time = float(match.source_time)
        if not any(start <= source_time <= end for start, end in intervals):
            total += sample_step_sec
    return total


def _pancake_vertical_padding_score(output: Path) -> tuple[float, dict[str, float]]:
    try:
        import cv2
    except ModuleNotFoundError:
        return 0.5, {"vertical_padding_checked_frames": 0.0}
    cap = cv2.VideoCapture(str(output))
    if not cap.isOpened():
        return 0.0, {"vertical_padding_checked_frames": 0.0}
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 30.0)
    frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    duration = frames / fps if fps > 0 else 0.0
    sample_times = [duration * frac for frac in [0.12, 0.22, 0.32, 0.42, 0.52, 0.62, 0.72, 0.82, 0.92] if duration > 0]
    checked = 0
    black_padding = 0
    blur_padding = 0
    landscape_blur_padding = 0
    for time_sec in sample_times:
        cap.set(cv2.CAP_PROP_POS_MSEC, time_sec * 1000.0)
        ok, frame = cap.read()
        if not ok:
            continue
        checked += 1
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        h, _w = gray.shape
        top = gray[: max(1, int(h * 0.22)), :]
        center = gray[int(h * 0.34) : max(int(h * 0.34) + 1, int(h * 0.66)), :]
        bottom = gray[int(h * 0.78) :, :]
        top_mean = float(np.mean(top))
        bottom_mean = float(np.mean(bottom))
        top_var = float(np.var(top))
        bottom_var = float(np.var(bottom))
        if (top_mean < 18.0 and top_var < 80.0) or (bottom_mean < 18.0 and bottom_var < 80.0):
            black_padding += 1
        top_lap = float(cv2.Laplacian(top, cv2.CV_64F).var())
        center_lap = float(cv2.Laplacian(center, cv2.CV_64F).var())
        bottom_lap = float(cv2.Laplacian(bottom, cv2.CV_64F).var())
        padding_lap = (top_lap + bottom_lap) / 2.0
        if center_lap > 80.0 and padding_lap < 70.0 and center_lap > padding_lap * 1.8:
            blur_padding += 1
        lap = np.abs(cv2.Laplacian(gray, cv2.CV_64F))
        row_edges = lap.mean(axis=1)
        kernel = max(9, int(h * 0.015) // 2 * 2 + 1)
        smoothed = np.convolve(row_edges, np.ones(kernel) / kernel, mode="same")
        upper_background = float(np.mean(smoothed[int(h * 0.14) : max(int(h * 0.14) + 1, int(h * 0.28))]))
        middle_band = float(np.mean(smoothed[int(h * 0.38) : max(int(h * 0.38) + 1, int(h * 0.62))]))
        lower_background = float(np.mean(smoothed[int(h * 0.72) : max(int(h * 0.72) + 1, int(h * 0.86))]))
        if (
            middle_band > 1.0
            and middle_band / max(1e-6, upper_background) > 1.45
            and middle_band / max(1e-6, lower_background) > 2.20
        ):
            landscape_blur_padding += 1
    cap.release()
    if checked <= 0:
        return 0.0, {"vertical_padding_checked_frames": 0.0}
    black_ratio = black_padding / checked
    blur_ratio = blur_padding / checked
    landscape_blur_ratio = landscape_blur_padding / checked
    score = 1.0 - max(black_ratio, 0.85 * blur_ratio, landscape_blur_ratio)
    return clamp01(score), {
        "vertical_padding_checked_frames": float(checked),
        "top_bottom_black_padding_ratio": float(black_ratio),
        "top_bottom_blur_padding_ratio": float(blur_ratio),
        "landscape_blur_padding_ratio": float(landscape_blur_ratio),
    }


def _apply_pancake_hard_caps(
    *,
    scores: dict[str, float],
    total: float,
    caps: dict[str, Any],
    fatal: bool,
) -> tuple[float, list[str]]:
    if fatal or scores.get("gate_output_exists", 0.0) < 1.0 or scores.get("gate_ffprobe_readable", 0.0) < 1.0:
        value = float(caps.get("missing_output_or_ffprobe", 0.0))
        scores["pancake_hard_cap_value"] = value
        scores["pancake_hard_cap_applied"] = 1.0
        return value, ["pancake hard cap 0.00: fatal media gate failure or missing/unreadable output"]

    cap = 1.0
    reasons: list[str] = []
    checks = [
        (scores.get("gate_has_audio_video", 0.0) < 1.0, "missing_audio_or_video", 0.25, "missing video or audio stream"),
        (scores.get("gate_duration_valid", 0.0) < 1.0, "duration_outside_gate", 0.50, "duration outside 50-70s gate"),
        (scores.get("gate_aspect_valid", 0.0) < 1.0, "wrong_aspect_or_resolution_family", 0.35, "not a portrait 9:16 deliverable"),
        (
            scores.get("top_bottom_black_padding_ratio", 0.0) > 0.25
            or scores.get("top_bottom_blur_padding_ratio", 0.0) > 0.35
            or scores.get("landscape_blur_padding_ratio", 0.0) > 0.30,
            "fake_or_weak_vertical",
            0.35,
            "portrait output appears to use black or blurred padding instead of a true vertical reframe",
        ),
        (scores.get("r_true_vertical_reframe", 0.0) < 0.65, "weak_vertical_reframe", 0.60, "vertical reframe is too weak or misses the cooking subject"),
        (scores.get("tutorial_impurity_ratio", 0.0) > 0.20, "heavy_negative_material", 0.40, "too much non-tutorial, novice, blooper, or end-card material leaked into output"),
        (scores.get("source_match_fraction", 0.0) < 0.45, "external_or_unmatched_material", 0.35, "too much output is unmatched to the source video"),
        (scores.get("r_visual_step_completeness", 0.0) < 0.40, "weak_visual_step_completeness", 0.55, "required tutorial step visual coverage is weak"),
        (scores.get("r_temporal_order", 0.0) < 0.50, "severe_order_failure", 0.60, "timeline or step order is severely degraded"),
        (scores.get("caption_visual_presence", 0.0) < 0.25, "missing_or_invisible_captions", 0.70, "captions are missing or not visibly burned in"),
        (
            scores.get("r_step_caption_completeness", 0.0) < 0.40 and scores.get("caption_visual_presence", 0.0) < 0.50,
            "weak_step_captions",
            0.65,
            "captions do not describe enough tutorial steps",
        ),
    ]
    for condition, key, default_value, reason in checks:
        if condition:
            value = float(caps.get(key, default_value))
            cap = min(cap, value)
            reasons.append(reason)

    if scores.get("llm_judge_available", 0.0) >= 1.0:
        llm_checks = [
            (scores.get("llm_step_caption_completeness", 1.0) < 0.30, 0.60, "LLM judged step captions as severely incomplete"),
            (scores.get("llm_caption_visual_alignment", 1.0) < 0.25, 0.55, "LLM judged captions as poorly aligned with the visible action"),
            (scores.get("llm_mobile_caption_readability", 1.0) < 0.25, 0.65, "LLM judged captions/framing as unreadable on mobile"),
            (scores.get("llm_prompt_fit", 1.0) < 0.30, 0.55, "LLM judged the output as not fitting the tutorial task"),
        ]
        for condition, value, reason in llm_checks:
            if condition:
                cap = min(cap, value)
                reasons.append(reason)

    scores["pancake_hard_cap_value"] = cap
    scores["pancake_hard_cap_applied"] = 1.0 if cap < 1.0 else 0.0
    if cap < 1.0:
        return min(total, cap), [f"pancake hard cap {cap:.2f}: " + "; ".join(reasons)]
    return total, []


def _score_piecewise_sync(
    run_id: str,
    task_id: str,
    agent: str,
    workspace: Path,
    repo: Path,
    ground_truth: dict[str, Any],
    config: dict[str, Any],
    schema: dict[str, Any],
    llm_judge: bool,
    llm_model: str | None,
) -> ScoreRecord:
    scores, context, notes, _fatal = _media_context(workspace, config)
    edit_score, edit, edit_notes = validate_json(workspace / "submit" / "edit_decision.json", schema)
    notes.extend(edit_notes)
    scores["edit_decision_schema"] = edit_score

    output = Path(context["output_path"])
    clean_reference = repo / "tasks" / task_id / "private" / "clean_reference.mp4"
    if not clean_reference.exists():
        notes.append("missing private/clean_reference.mp4; full A/V residual verifier cannot run")
        clean_reference = Path(context["source_path"])

    residual_matches = []
    if output.exists() and clean_reference.exists():
        residual_matches = sync_residual_matches(output=output, clean_reference=clean_reference)
    else:
        notes.append("output or clean reference missing; sync residual matching skipped")

    scores["r_av_sync_global"] = _score_sync_residuals(
        residual_matches,
        expected_anchors=float(config.get("expected_sync_anchors", 12.0)),
        prefix="r_av_sync_global",
        scores=scores,
    )
    scores["r_av_sync_segmented"] = _score_segmented_sync(
        residual_matches,
        segments=config.get("sync_segments"),
        scores=scores,
    )
    scores["sync_median_residual_ms"] = scores.get("r_av_sync_global_median_ms", 999.0)
    scores["sync_p90_residual_ms"] = scores.get("r_av_sync_global_p90_ms", 999.0)
    scores["sync_anchor_match_coverage"] = scores.get("r_av_sync_global_anchor_coverage", 0.0)
    scores["local_av_sync_repair"] = clamp01(0.5 * scores["r_av_sync_global"] + 0.5 * scores["r_av_sync_segmented"])

    video_matches = []
    if output.exists() and clean_reference.exists():
        video_matches = match_video_timeline(output=output, source=clean_reference, output_fps=1.0, source_fps=1.0, threshold=0.55)
    if not video_matches:
        notes.append("clean-reference visual matching found no confident matches")

    scores["r_black_boundary_cleanup"] = _black_boundary_cleanup_score(output, scores)
    scores["r_freeze_dead_air_cleanup"] = _freeze_dead_air_cleanup_score(
        output=output,
        video_matches=video_matches,
        context=context,
        ground_truth=ground_truth,
        scores=scores,
    )
    scores["r_visual_artifact_cleanup"] = _visual_artifact_cleanup_score(output=output, scores=scores, context=context)
    scores["r_duplicate_or_bad_insert_cleanup"] = _duplicate_or_bad_insert_cleanup_score(
        video_matches=video_matches,
        ground_truth=ground_truth,
        scores=scores,
    )
    scores["r_content_preservation"] = _content_preservation_score(
        video_matches=video_matches,
        ground_truth=ground_truth,
        duration_target_score=scores.get("duration_target_score", 0.0),
        scores=scores,
        config=config,
    )

    scores["r_format"] = _format_score(scores)
    scores["format_compliance"] = scores["r_format"]
    scores["r_audio_quality"] = scores.get("audio_quality", 0.0)
    scores["r_audio_cleanup"] = clamp01(0.75 * scores["r_audio_quality"] + 0.25 * scores.get("r_no_dead_air", 0.0))
    scores["r_artifact_completeness"] = _artifact_completeness_score(scores=scores, edit_score=edit_score)
    scores["r_provenance_and_logs"] = _provenance_and_logs_score(edit=edit, edit_score=edit_score, scores=scores)
    scores["sync_repair_signal"] = clamp01(0.55 * scores["r_av_sync_global"] + 0.45 * scores["r_av_sync_segmented"])
    scores["r_reasoning_plan"] = _reasoning_plan_score(edit=edit, edit_score=edit_score, scores=scores)
    scores["r_tool_use_execution"] = _tool_use_execution_score(edit=edit, scores=scores)
    scores["r_multimodal_grounding"] = _multimodal_grounding_score(scores)
    general_weights = config.get(
        "general_weights",
        {
            "r_format": 0.40,
            "r_audio_quality": 0.25,
            "r_artifact_completeness": 0.20,
            "r_provenance_and_logs": 0.15,
        },
    )
    task_weights = config.get(
        "task_weights",
        {
            "r_av_sync_segmented": 0.22,
            "r_av_sync_global": 0.18,
            "r_visual_artifact_cleanup": 0.18,
            "r_content_preservation": 0.16,
            "r_duplicate_or_bad_insert_cleanup": 0.12,
            "r_audio_cleanup": 0.08,
            "r_black_boundary_cleanup": 0.06,
        },
    )
    scores["r_general"] = _weighted_score(scores, general_weights)
    scores["r_hard_task"] = _weighted_score(scores, task_weights)
    scores["r_task_hard"] = scores["r_hard_task"]
    scores["content_preservation_damage_cleanup"] = clamp01(
        0.55 * scores["r_content_preservation"]
        + 0.25 * scores["r_freeze_dead_air_cleanup"]
        + 0.20 * scores["r_black_boundary_cleanup"]
    )
    scores["deliverable_quality_explainability"] = scores["r_general"]
    scores["r_llm_proxy"] = clamp01(
        0.40 * scores["local_av_sync_repair"]
        + 0.35 * scores["content_preservation_damage_cleanup"]
        + 0.25 * scores["deliverable_quality_explainability"]
    )
    scores["r_llm"] = scores["r_llm_proxy"]

    if llm_judge:
        llm_scores, llm_notes, _raw = maybe_run_llm_judge(
            task_id=task_id,
            workspace=workspace,
            hard_scores=scores,
            edit_decision=edit,
            enabled=True,
            model=llm_model,
        )
        scores.update(llm_scores)
        notes.extend(llm_notes)
        if scores.get("llm_judge_available", 0.0) >= 1.0:
            scores["r_llm"] = scores.get("llm_overall", 0.0)

    hard_task_weight = float(config.get("hard_task_weight", 0.85))
    llm_weight = float(config.get("llm_weight", 0.15))
    scores["r_llm_task"] = scores["r_llm"]
    scores["r_task"] = clamp01(
        hard_task_weight * scores["r_hard_task"]
        + llm_weight * scores["r_llm_task"]
    )
    total = clamp01(
        float(config.get("general_weight", 0.20)) * scores["r_general"]
        + float(config.get("task_weight", 0.80)) * scores["r_task"]
    )
    scores["r_final_before_caps"] = total
    total, cap_notes = _apply_piecewise_hard_caps(scores=scores, total=total, caps=config.get("hard_caps", {}))
    notes.extend(cap_notes)
    scores["r_final_after_caps"] = total

    return ScoreRecord(run_id=run_id, task_id=task_id, agent=agent, scores=scores, total=clamp01(total), notes=_verifier_notes(notes))


def _score_sync_residuals(
    residual_matches: list[Any],
    *,
    expected_anchors: float,
    prefix: str,
    scores: dict[str, float],
) -> float:
    residuals = [abs(float(item.residual_ms)) for item in residual_matches]
    correlations = [float(item.correlation) for item in residual_matches]
    if residuals:
        sorted_residuals = sorted(residuals)
        median_residual = float(np.median(sorted_residuals))
        p90_residual = float(np.percentile(sorted_residuals, 90))
        median_correlation = float(np.median(correlations)) if correlations else 0.0
    else:
        median_residual = 999.0
        p90_residual = 999.0
        median_correlation = 0.0
    anchor_coverage = clamp01(len(residuals) / max(1.0, expected_anchors))
    residual_score = clamp01(
        0.65 * _sync_residual_quality(median_residual)
        + 0.35 * _sync_residual_quality(p90_residual)
    )
    correlation_score = ramp_score(median_correlation, good=0.22, bad=0.08, lower_is_better=False)
    scores[f"{prefix}_anchor_count"] = float(len(residuals))
    scores[f"{prefix}_anchor_coverage"] = anchor_coverage
    scores[f"{prefix}_median_ms"] = median_residual
    scores[f"{prefix}_p90_ms"] = p90_residual
    scores[f"{prefix}_median_correlation"] = median_correlation
    return clamp01(residual_score * anchor_coverage * (0.85 + 0.15 * correlation_score))


def _sync_residual_quality(residual_ms: float) -> float:
    """Long-tail A/V sync score so mediocre repairs do not collapse to all-zero."""
    residual = abs(float(residual_ms))
    if residual <= 80.0:
        return 1.0
    if residual <= 250.0:
        return 1.0 - 0.30 * ((residual - 80.0) / 170.0)
    if residual <= 600.0:
        return 0.70 - 0.45 * ((residual - 250.0) / 350.0)
    if residual <= 1000.0:
        return 0.25 - 0.20 * ((residual - 600.0) / 400.0)
    if residual <= 1600.0:
        return 0.05 * (1.0 - ((residual - 1000.0) / 600.0))
    return 0.0


def _weighted_score(scores: dict[str, float], weights: dict[str, Any]) -> float:
    total_weight = sum(max(0.0, float(weight)) for weight in weights.values())
    if total_weight <= 0:
        return 0.0
    return clamp01(
        sum(scores.get(key, 0.0) * max(0.0, float(weight)) for key, weight in weights.items()) / total_weight
    )


def _score_segmented_sync(
    residual_matches: list[Any],
    *,
    segments: list[dict[str, Any]] | None,
    scores: dict[str, float],
) -> float:
    if not segments:
        segments = [
            {"id": "opening", "interval": [0.0, 31.5], "weight": 0.35},
            {"id": "middle_pre_splice", "interval": [31.5, 47.5], "weight": 0.175},
            {"id": "middle_post_splice", "interval": [47.5, 63.0], "weight": 0.175},
            {"id": "late", "interval": [63.0, 96.0], "weight": 0.30},
        ]

    weighted = 0.0
    weight_total = 0.0
    for segment in segments:
        start, end = (float(value) for value in segment["interval"])
        weight = float(segment.get("weight", max(0.0, end - start)))
        segment_id = re.sub(r"[^a-zA-Z0-9_]+", "_", str(segment.get("id", f"{start}_{end}"))).strip("_")
        segment_matches = [
            item
            for item in residual_matches
            if start <= float(item.source_time) <= end
        ]
        expected = max(2.0, (end - start) / 8.0)
        segment_score = _score_sync_residuals(
            segment_matches,
            expected_anchors=expected,
            prefix=f"r_av_sync_segmented_{segment_id}",
            scores=scores,
        )
        scores[f"r_av_sync_segmented_{segment_id}"] = segment_score
        weighted += weight * segment_score
        weight_total += weight
    return clamp01(weighted / max(1e-9, weight_total))


def _black_boundary_cleanup_score(output: Path, scores: dict[str, float]) -> float:
    leader_ratio = _black_frame_ratio_in_window(output, start_sec=0.0, end_sec=1.0)
    duration = _cv2_duration(output)
    tail_ratio = _black_frame_ratio_in_window(output, start_sec=max(0.0, duration - 1.0), end_sec=duration) if duration > 0 else 1.0
    leader_score = ramp_score(leader_ratio, good=0.02, bad=0.40)
    tail_score = ramp_score(tail_ratio, good=0.02, bad=0.40)
    scores["black_leader_ratio"] = leader_ratio
    scores["black_tail_ratio"] = tail_ratio
    scores["r_no_black_leader"] = leader_score
    scores["r_no_black_tail"] = tail_score
    return clamp01(0.5 * leader_score + 0.5 * tail_score)


def _freeze_dead_air_cleanup_score(
    *,
    output: Path,
    video_matches: list[Any],
    context: dict[str, Any],
    ground_truth: dict[str, Any],
    scores: dict[str, float],
) -> float:
    vstats = context.get("video_stats", {})
    astats = context.get("audio_stats", {})
    global_no_freeze = ramp_score(float(vstats.get("max_frozen_run_sec", 999.0)), good=0.5, bad=4.0)
    no_dead_air = ramp_score(float(astats.get("max_silence_sec", 999.0)), good=1.2, bad=4.0)

    splice_clean_time = float(
        ground_truth.get("corruption_recipe", {})
        .get("freeze_splice", {})
        .get("clean_time_sec", 47.5)
    )
    splice_output_time = _estimate_output_time_for_source(video_matches, source_time=splice_clean_time)
    if splice_output_time is None:
        splice_no_freeze = 0.5
        local_freeze = 999.0
        local_black = 1.0
    else:
        local_stats = _video_window_stats(output, start_sec=max(0.0, splice_output_time - 1.5), end_sec=splice_output_time + 1.5)
        local_freeze = local_stats["max_frozen_run_sec"]
        local_black = local_stats["black_frame_ratio"]
        splice_no_freeze = clamp01(
            0.85 * ramp_score(local_freeze, good=0.12, bad=0.55)
            + 0.15 * ramp_score(local_black, good=0.01, bad=0.35)
        )

    local_silence = _audio_max_silence_in_window(output, start_sec=max(0.0, (splice_output_time or 47.5) - 2.0), end_sec=(splice_output_time or 47.5) + 2.0)
    splice_dead_air = ramp_score(local_silence, good=0.45, bad=1.4)
    timeline_continuity = scores.get("source_time_monotonicity", timeline_monotonicity(video_matches))

    scores["global_max_frozen_run_sec"] = float(vstats.get("max_frozen_run_sec", 999.0))
    scores["global_max_silence_sec"] = float(astats.get("max_silence_sec", 999.0))
    scores["freeze_splice_estimated_output_time"] = float(splice_output_time) if splice_output_time is not None else -1.0
    scores["freeze_splice_max_frozen_run_sec"] = local_freeze
    scores["freeze_splice_black_ratio"] = local_black
    scores["freeze_splice_max_silence_sec"] = local_silence
    scores["r_global_no_freeze"] = global_no_freeze
    scores["r_no_dead_air"] = no_dead_air
    scores["r_splice_no_freeze"] = splice_no_freeze
    scores["r_splice_no_dead_air"] = splice_dead_air
    scores["r_timeline_continuity"] = timeline_continuity
    return clamp01(
        0.22 * global_no_freeze
        + 0.43 * splice_no_freeze
        + 0.20 * no_dead_air
        + 0.10 * splice_dead_air
        + 0.05 * timeline_continuity
    )


def _visual_artifact_cleanup_score(*, output: Path, scores: dict[str, float], context: dict[str, Any]) -> float:
    duration = _cv2_duration(output)
    if duration <= 0:
        scores["bright_flash_frame_ratio"] = 1.0
        scores["r_no_bright_flash"] = 0.0
        return 0.0
    window_stats = _video_window_stats(output, start_sec=0.0, end_sec=duration, sample_fps=8.0)
    bright_ratio = float(window_stats.get("bright_frame_ratio", 1.0))
    no_bright_flash = ramp_score(bright_ratio, good=0.002, bad=0.012)
    global_no_freeze = scores.get(
        "r_global_no_freeze",
        ramp_score(float(context.get("video_stats", {}).get("max_frozen_run_sec", 999.0)), good=0.5, bad=4.0),
    )
    splice_no_freeze = scores.get("r_splice_no_freeze", 0.0)
    scores["bright_flash_frame_ratio"] = bright_ratio
    scores["r_no_bright_flash"] = no_bright_flash
    return clamp01(0.35 * global_no_freeze + 0.35 * splice_no_freeze + 0.30 * no_bright_flash)


def _duplicate_or_bad_insert_cleanup_score(
    *,
    video_matches: list[Any],
    ground_truth: dict[str, Any],
    scores: dict[str, float],
) -> float:
    duplicate = ground_truth.get("corruption_recipe", {}).get("duplicate_insert")
    if not duplicate:
        scores["duplicate_interval_match_ratio"] = 1.0
        scores["r_duplicate_interval_presence"] = 1.0
        scores["r_duplicate_interval_not_overused"] = 1.0
        return scores.get("source_time_monotonicity", timeline_monotonicity(video_matches))

    start = float(duplicate["clean_start_sec"])
    end = float(duplicate["clean_end_sec"])
    duration = max(0.1, end - start)
    matched_seconds = seconds_in_intervals(video_matches, [(start, end)], sample_step_sec=1.0)
    match_ratio = matched_seconds / duration
    presence_score = ramp_score(match_ratio, good=0.75, bad=0.25, lower_is_better=False)
    not_overused_score = ramp_score(match_ratio, good=1.25, bad=1.90)
    monotonicity = scores.get("source_time_monotonicity", timeline_monotonicity(video_matches))
    scores["duplicate_interval_matched_sec"] = matched_seconds
    scores["duplicate_interval_match_ratio"] = match_ratio
    scores["r_duplicate_interval_presence"] = presence_score
    scores["r_duplicate_interval_not_overused"] = not_overused_score
    return clamp01(0.35 * presence_score + 0.45 * not_overused_score + 0.20 * monotonicity)


def _content_preservation_score(
    *,
    video_matches: list[Any],
    ground_truth: dict[str, Any],
    duration_target_score: float,
    scores: dict[str, float],
    config: dict[str, Any],
) -> float:
    span_items = ground_truth.get("required_spans", [])
    full_credit_fraction = float(config.get("content_full_credit_fraction", 0.90))
    weighted_span_score = 0.0
    weight_total = 0.0
    min_span_score = 1.0 if span_items else 0.0
    weighted_coverage_seconds = 0.0
    weighted_required_seconds = 0.0
    for span in span_items:
        span_id = re.sub(r"[^a-zA-Z0-9_]+", "_", str(span.get("id", "span"))).strip("_")
        interval = tuple(float(x) for x in span["interval"])
        duration = max(0.0, interval[1] - interval[0])
        weight = float(span.get("weight", duration))
        covered = seconds_in_intervals(video_matches, [interval], sample_step_sec=1.0)
        span_score = clamp01(covered / max(1.0, duration * full_credit_fraction))
        scores[f"required_span_{span_id}_covered_sec"] = covered
        scores[f"required_span_{span_id}_score"] = span_score
        weighted_span_score += weight * span_score
        weight_total += weight
        min_span_score = min(min_span_score, span_score)
        weighted_coverage_seconds += weight * min(covered, duration)
        weighted_required_seconds += weight * duration
    required_span_coverage = clamp01(weighted_span_score / max(1e-9, weight_total))
    raw_required_span_coverage = clamp01(weighted_coverage_seconds / max(1e-9, weighted_required_seconds))
    source_time_monotonicity = timeline_monotonicity(video_matches)
    scores["required_span_coverage"] = required_span_coverage
    scores["required_span_raw_coverage"] = raw_required_span_coverage
    scores["required_span_min_score"] = min_span_score
    scores["source_time_monotonicity"] = source_time_monotonicity
    return clamp01(
        0.60 * required_span_coverage
        + 0.25 * source_time_monotonicity
        + 0.15 * duration_target_score
    )


def _artifact_completeness_score(*, scores: dict[str, float], edit_score: float) -> float:
    return clamp01(
        0.35 * scores.get("gate_output_exists", 0.0)
        + 0.20 * edit_score
        + 0.20 * scores.get("gate_ffprobe_readable", 0.0)
        + 0.125 * scores.get("run_history_exists", 0.0)
        + 0.125 * scores.get("agent_transcript_exists", 0.0)
    )


def _as_text_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, dict):
        return [f"{key}: {val}" for key, val in value.items()]
    if value:
        return [str(value)]
    return []


def _present_nonempty(value: Any) -> float:
    if isinstance(value, (list, dict)):
        return float(len(value) > 0)
    return float(bool(value))


def _reason_coverage(edit: dict[str, Any]) -> float:
    inspected: list[dict[str, Any]] = []
    for key in ("operations", "segments", "local_audio_shifts_ms", "removed_damage_ranges", "audio_filters"):
        value = edit.get(key)
        if isinstance(value, list):
            inspected.extend(item for item in value if isinstance(item, dict))
    if not inspected:
        return 0.0
    reasoned = 0
    for item in inspected:
        reason = str(item.get("reason") or item.get("description") or "")
        reasoned += int(len(reason.strip()) >= 12)
    return clamp01(reasoned / len(inspected))


def _checks_performed_score(edit: dict[str, Any]) -> float:
    checks_text = " ".join(_as_text_list(edit.get("checks_performed")) + _as_text_list(edit.get("self_checks"))).lower()
    if not checks_text:
        return 0.0
    expected_evidence = [
        ("ffprobe", "probe", "metadata", "codec", "stream"),
        ("duration", "fps", "resolution", "aspect", "sar", "dar"),
        ("audio", "loudness", "rms", "clip", "silence"),
        ("frame", "black", "freeze", "contact sheet", "opencv", "cv2"),
        ("sync", "offset", "shift", "residual", "clap", "transient"),
    ]
    hits = 0
    for terms in expected_evidence:
        hits += int(any(term in checks_text for term in terms))
    return clamp01(hits / len(expected_evidence))


def _tool_category_score(edit: dict[str, Any]) -> float:
    tools_text = " ".join(_as_text_list(edit.get("tools_used"))).lower()
    if not tools_text:
        return 0.0
    categories = [
        ("ffprobe",),
        ("ffmpeg", "moviepy", "pyav", "av"),
        ("python", "script", "bash"),
        ("librosa", "scipy", "pydub", "soundfile", "noisereduce"),
        ("opencv", "cv2", "pillow", "pil", "skimage", "imageio"),
    ]
    hits = 0
    for terms in categories:
        hits += int(any(term in tools_text for term in terms))
    return clamp01(hits / len(categories))


def _reasoning_plan_score(*, edit: dict[str, Any], edit_score: float, scores: dict[str, float]) -> float:
    plan_field_score = clamp01(
        (
            _present_nonempty(edit.get("segments"))
            + _present_nonempty(edit.get("local_audio_shifts_ms"))
            + _present_nonempty(edit.get("removed_damage_ranges"))
        )
        / 3.0
    )
    return clamp01(
        0.40 * plan_field_score
        + 0.25 * _reason_coverage(edit)
        + 0.20 * edit_score
        + 0.15 * scores.get("run_history_exists", 0.0)
    )


def _tool_use_execution_score(*, edit: dict[str, Any], scores: dict[str, float]) -> float:
    return clamp01(
        0.45 * _tool_category_score(edit)
        + 0.35 * _checks_performed_score(edit)
        + 0.20 * scores.get("r_artifact_completeness", 0.0)
    )


def _multimodal_grounding_score(scores: dict[str, float]) -> float:
    return clamp01(
        0.45 * scores.get("sync_repair_signal", 0.0)
        + 0.20 * scores.get("r_content_preservation", 0.0)
        + 0.15 * scores.get("r_freeze_dead_air_cleanup", 0.0)
        + 0.10 * scores.get("r_black_boundary_cleanup", 0.0)
        + 0.10 * scores.get("r_audio_quality", 0.0)
    )


def _provenance_and_logs_score(*, edit: dict[str, Any], edit_score: float, scores: dict[str, float]) -> float:
    required_values = [
        edit.get("source_files"),
        edit.get("tools_used"),
        edit.get("checks_performed") or edit.get("self_checks"),
        edit.get("segments"),
        edit.get("local_audio_shifts_ms"),
        edit.get("removed_damage_ranges"),
    ]
    field_presence = sum(_present_nonempty(value) for value in required_values) / len(required_values)
    scores["edit_decision_required_field_presence"] = field_presence
    return clamp01(
        0.50 * field_presence
        + 0.30 * edit_score
        + 0.20 * scores.get("run_history_transcript_score", 0.0)
    )


def _apply_piecewise_hard_caps(*, scores: dict[str, float], total: float, caps: dict[str, Any]) -> tuple[float, list[str]]:
    notes: list[str] = []
    cap = 1.0
    reasons: list[str] = []

    if scores.get("gate_output_exists", 0.0) < 1.0 or scores.get("gate_ffprobe_readable", 0.0) < 1.0:
        scores["hard_cap_value"] = float(caps.get("missing_output_or_ffprobe", 0.0))
        scores["hard_cap_applied"] = 1.0
        return scores["hard_cap_value"], ["hard cap 0.00: missing output or ffprobe-unreadable output"]

    checks = [
        (scores.get("gate_has_audio_video", 0.0) < 1.0, "missing_audio_or_video", 0.25, "missing video or audio stream"),
        (scores.get("gate_duration_valid", 0.0) < 1.0, "duration_outside_gate", 0.50, "duration outside 88-98s gate"),
        (scores.get("gate_aspect_valid", 0.0) < 1.0, "wrong_aspect_or_resolution_family", 0.60, "wrong aspect or resolution family"),
        (scores.get("gate_non_degenerate_video", 0.0) < 1.0, "degenerate_video", 0.50, "degenerate black/frozen video"),
        (scores.get("gate_non_degenerate_audio", 0.0) < 1.0, "degenerate_audio", 0.50, "degenerate silent/clipped audio"),
        (scores.get("r_hard_task", scores.get("r_task", 0.0)) < 0.30, "task_below_0_30", 0.45, "r_hard_task below 0.30"),
        (scores.get("r_content_preservation", 0.0) < 0.70, "content_preservation_below_0_70", 0.60, "r_content_preservation below 0.70"),
        (scores.get("required_span_coverage", 0.0) < 0.85, "required_span_coverage_below_0_85", 0.60, "required span coverage below 0.85"),
        (scores.get("required_span_min_score", 0.0) < 0.75, "any_required_span_below_0_75", 0.70, "at least one required span below 0.75"),
        (scores.get("source_time_monotonicity", 0.0) < 0.80, "source_time_monotonicity_below_0_80", 0.65, "source time monotonicity below 0.80"),
        (scores.get("r_black_boundary_cleanup", 0.0) < 0.50, "black_boundary_cleanup_below_0_50", 0.70, "r_black_boundary_cleanup below 0.50"),
        (scores.get("r_visual_artifact_cleanup", 0.0) < 0.50, "visual_artifact_cleanup_below_0_50", 0.70, "r_visual_artifact_cleanup below 0.50"),
        (scores.get("r_duplicate_or_bad_insert_cleanup", 0.0) < 0.50, "duplicate_cleanup_below_0_50", 0.70, "r_duplicate_or_bad_insert_cleanup below 0.50"),
        (scores.get("r_audio_cleanup", 0.0) < 0.40, "audio_cleanup_below_0_40", 0.75, "r_audio_cleanup below 0.40"),
    ]
    sync_global = scores.get("r_av_sync_global", 0.0)
    sync_segmented = scores.get("r_av_sync_segmented", 0.0)
    sync_repair_signal = clamp01(0.55 * sync_global + 0.45 * sync_segmented)
    scores["sync_repair_signal"] = sync_repair_signal
    for condition, key, default_value, reason in checks:
        if condition:
            value = float(caps.get(key, default_value))
            cap = min(cap, value)
            reasons.append(reason)

    scores["hard_cap_value"] = cap
    scores["hard_cap_applied"] = 1.0 if cap < 1.0 else 0.0
    capped_total = min(total, cap)
    if cap < 1.0:
        notes.append(f"hard cap {cap:.2f}: " + "; ".join(reasons))
    return capped_total, notes


def _sync_failure_cap(*, sync_global: float, sync_segmented: float) -> float | None:
    signal = clamp01(0.55 * sync_global + 0.45 * sync_segmented)
    best = max(sync_global, sync_segmented)
    if best < 0.10:
        return 0.35 + 0.50 * best
    if signal < 0.20:
        return 0.35 + 0.70 * max(0.0, signal - 0.10)
    if signal < 0.30:
        return 0.42 + 0.80 * (signal - 0.20)
    return None


def _black_frame_ratio_in_window(output: Path, *, start_sec: float, end_sec: float) -> float:
    return _video_window_stats(output, start_sec=start_sec, end_sec=end_sec)["black_frame_ratio"]


def _video_window_stats(output: Path, *, start_sec: float, end_sec: float, sample_fps: float = 8.0) -> dict[str, float]:
    try:
        import cv2
    except ModuleNotFoundError:
        return {"black_frame_ratio": 1.0, "bright_frame_ratio": 1.0, "max_frozen_run_sec": 999.0}

    cap = cv2.VideoCapture(str(output))
    if not cap.isOpened():
        return {"black_frame_ratio": 1.0, "bright_frame_ratio": 1.0, "max_frozen_run_sec": 999.0}
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 30.0)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    if fps <= 0:
        cap.release()
        return {"black_frame_ratio": 1.0, "bright_frame_ratio": 1.0, "max_frozen_run_sec": 999.0}
    start_frame = max(0, int(round(start_sec * fps)))
    end_frame = min(total_frames, int(round(end_sec * fps))) if total_frames else int(round(end_sec * fps))
    step = max(1, int(round(fps / max(0.1, sample_fps))))
    cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)

    sampled = 0
    black = 0
    bright = 0
    frozen_run = 0
    max_frozen_run = 0
    prev_small = None
    frame_idx = start_frame
    while frame_idx < end_frame:
        ok, frame = cap.read()
        if not ok:
            break
        if (frame_idx - start_frame) % step == 0:
            sampled += 1
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            mean = float(np.mean(gray))
            var = float(np.var(gray))
            if mean < 10.0 and var < 20.0:
                black += 1
            if mean > 240.0 and var < 35.0:
                bright += 1
            small = cv2.resize(gray, (96, 54), interpolation=cv2.INTER_AREA)
            if prev_small is not None:
                diff = float(np.mean(np.abs(small.astype(np.float32) - prev_small.astype(np.float32))))
                if diff < 0.25:
                    frozen_run += 1
                    max_frozen_run = max(max_frozen_run, frozen_run)
                else:
                    frozen_run = 0
            prev_small = small
        frame_idx += 1
    cap.release()
    sample_interval = step / fps
    if sampled <= 0:
        return {"black_frame_ratio": 1.0, "bright_frame_ratio": 1.0, "max_frozen_run_sec": 999.0}
    return {
        "black_frame_ratio": black / sampled,
        "bright_frame_ratio": bright / sampled,
        "max_frozen_run_sec": max_frozen_run * sample_interval,
    }


def _cv2_duration(output: Path) -> float:
    try:
        import cv2
    except ModuleNotFoundError:
        return 0.0
    cap = cv2.VideoCapture(str(output))
    if not cap.isOpened():
        return 0.0
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
    frames = float(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0.0)
    cap.release()
    if fps <= 0:
        return 0.0
    return frames / fps


def _audio_max_silence_in_window(output: Path, *, start_sec: float, end_sec: float, sample_rate: int = 16000) -> float:
    try:
        samples = read_audio_mono(output, sample_rate=sample_rate)
    except Exception:  # noqa: BLE001
        return 999.0
    if samples.size == 0:
        return 999.0
    start = max(0, int(round(start_sec * sample_rate)))
    end = min(samples.size, int(round(end_sec * sample_rate)))
    if end <= start:
        return 999.0
    window = samples[start:end]
    frame_len = max(1, int(sample_rate * 0.05))
    usable = window[: (window.size // frame_len) * frame_len]
    if usable.size == 0:
        return window.size / sample_rate
    rms = float(np.sqrt(np.mean(np.square(samples))))
    rms_dbfs = 20.0 * np.log10(max(rms, 1e-9))
    frames = usable.reshape((-1, frame_len))
    frame_rms = np.sqrt(np.mean(np.square(frames), axis=1))
    frame_db = 20.0 * np.log10(np.maximum(frame_rms, 1e-9))
    silence_threshold = min(-35.0, float(rms_dbfs) - 18.0)
    silent = frame_db < silence_threshold
    max_run = 0
    current = 0
    for is_silent in silent:
        if bool(is_silent):
            current += 1
            max_run = max(max_run, current)
        else:
            current = 0
    return max_run * frame_len / sample_rate


def _estimate_output_time_for_source(video_matches: list[Any], *, source_time: float) -> float | None:
    if not video_matches:
        return None
    close = [match for match in video_matches if abs(float(match.source_time) - source_time) <= 4.0]
    if close:
        best = min(close, key=lambda item: abs(float(item.source_time) - source_time))
        return float(best.output_time)
    before = [match for match in video_matches if float(match.source_time) <= source_time]
    after = [match for match in video_matches if float(match.source_time) >= source_time]
    if before and after:
        left = max(before, key=lambda item: float(item.source_time))
        right = min(after, key=lambda item: float(item.source_time))
        left_source = float(left.source_time)
        right_source = float(right.source_time)
        if right_source <= left_source + 1e-6:
            return float(left.output_time)
        ratio = (source_time - left_source) / (right_source - left_source)
        return float(left.output_time) + ratio * (float(right.output_time) - float(left.output_time))
    return None


def _score_interview(
    run_id: str,
    task_id: str,
    agent: str,
    workspace: Path,
    repo: Path,
    ground_truth: dict[str, Any],
    config: dict[str, Any],
    schema: dict[str, Any],
    llm_judge: bool,
    llm_model: str | None,
) -> ScoreRecord:
    scores, context, notes, fatal = _media_context(workspace, config)
    edit_score, edit, edit_notes = validate_json(workspace / "submit" / "edit_decision.json", schema)
    notes.extend(edit_notes)
    scores["edit_decision_schema"] = edit_score

    output = Path(context["output_path"])
    source = Path(context["source_path"])
    matches = match_video_timeline(output=output, source=source, output_fps=1.0, source_fps=1.0, threshold=0.55)
    if not matches:
        notes.append("rough-source visual matching found no confident matches")
    public_defects = _interview_defect_public_intervals(repo=repo, task_id=task_id, ground_truth=ground_truth)
    dead_air_intervals = [(item["public_start"], item["public_end"]) for item in public_defects if item["kind"] == "inserted_dead_air"]
    repeat_intervals = [(item["public_start"], item["public_end"]) for item in public_defects if item["kind"] == "repeated_phrase_loop"]
    dead_air_total = sum(end - start for start, end in dead_air_intervals)
    repeat_total = sum(end - start for start, end in repeat_intervals)
    dead_air_kept = seconds_in_intervals(matches, dead_air_intervals, sample_step_sec=1.0) if dead_air_intervals else 0.0
    repeat_kept = seconds_in_intervals(matches, repeat_intervals, sample_step_sec=1.0) if repeat_intervals else 0.0
    scores["inserted_pause_removed_ratio"] = 1.0 - clamp01(dead_air_kept / max(0.1, dead_air_total))
    scores["repeat_loop_suppression"] = 1.0 - clamp01(repeat_kept / max(0.1, repeat_total))
    scores["source_match_fraction"] = matched_fraction(matches, output_duration=float(context.get("duration", 0.0)), sample_step_sec=1.0)

    srt_entries = parse_srt(workspace / "submit" / "captions.srt")
    srt_body = srt_text(srt_entries)
    asr_data, asr_notes = transcribe_video(output, cache_path=workspace / "_logs" / "output_asr.json")
    notes.extend(asr_notes)
    asr_text = str(asr_data.get("text", "")) if asr_data else ""
    scores["asr_available"] = 1.0 if asr_data else 0.0
    combined_text = f"{asr_text} {srt_body} {_caption_text(edit)}".lower()
    tokens = _tokens(combined_text)
    semantic_scores = _semantic_anchor_scores(ground_truth["semantic_anchors"], combined_text)
    scores.update(semantic_scores)
    scores["duplicate_ngram_rate"] = _duplicate_ngram_rate(tokens, n=3)
    scores["semantic_anchor_preservation"] = clamp01(
        0.65 * scores["semantic_anchor_recall"]
        + 0.20 * scores["semantic_anchor_order"]
        + 0.15 * scores["semantic_anchor_diversity"]
    )

    scores["srt_valid"] = 1.0 if srt_entries else 0.0
    caption_duration = sum(max(0.0, float(entry["end"]) - float(entry["start"])) for entry in srt_entries)
    output_duration = max(1.0, float(context.get("duration", 1.0)))
    cue_times = [(float(entry["start"]) + float(entry["end"])) / 2.0 for entry in srt_entries]
    scores["caption_visibility"] = burned_caption_visibility_score(output, cue_times)
    layout_score, layout_details = caption_layout_occlusion_score(output, cue_times)
    scores.update(layout_details)
    scores["r_no_face_or_subject_occlusion"] = layout_score
    scores["srt_timing_coverage"] = clamp01(caption_duration / (output_duration * 0.70))
    caption_word_count_score = 1.0 if len(srt_body.split()) >= 80 else len(srt_body.split()) / 80.0
    scores["caption_word_count_score"] = caption_word_count_score
    srt_asr_scores = _srt_asr_alignment_scores(srt_entries=srt_entries, asr_data=asr_data)
    scores.update(srt_asr_scores)
    scores["caption_hard_quality"] = clamp01(
        0.18 * scores["srt_valid"]
        + 0.18 * scores["srt_timing_coverage"]
        + 0.14 * caption_word_count_score
        + 0.14 * scores["caption_visibility"]
        + 0.18 * scores["srt_asr_token_f1"]
        + 0.18 * scores["srt_asr_timed_token_f1"]
    )
    scores["speech_cleanup_hard"] = clamp01(
        0.30 * scores["inserted_pause_removed_ratio"]
        + 0.25 * scores["repeat_loop_suppression"]
        + 0.20 * (1.0 - scores["duplicate_ngram_rate"])
        + 0.15 * ramp_score(float(context.get("audio_stats", {}).get("max_silence_sec", 999.0)), good=1.2, bad=4.0)
        + 0.10 * scores["source_match_fraction"]
    )
    scores["audio_normalization"] = scores.get("audio_quality", 0.0)
    scores["speech_cleanup_semantic_preservation"] = clamp01(
        0.42 * scores["speech_cleanup_hard"]
        + 0.38 * scores["semantic_anchor_preservation"]
        + 0.20 * (1.0 - scores["duplicate_ngram_rate"])
    )
    scores["caption_audio_deliverable_quality"] = clamp01(
        0.72 * scores["caption_hard_quality"]
        + 0.18 * scores.get("audio_quality", 0.0)
        + 0.10 * scores["r_no_face_or_subject_occlusion"]
    )
    scores["source_fidelity_format_naturalness"] = clamp01(
        0.28 * _format_score(scores)
        + 0.20 * scores["source_match_fraction"]
        + 0.16 * scores.get("video_integrity", 0.0)
        + 0.14 * scores.get("audio_quality", 0.0)
        + 0.12 * edit_score
        + 0.10 * scores.get("run_history_transcript_score", 0.0)
    )
    scores["format_compliance"] = _format_score(scores)
    scores["r_format"] = scores["format_compliance"]
    scores.update(_interview_evidence_and_check_scores(edit=edit, scores=scores))
    scores.update(
        _interview_anti_reward_hack_scores(
            edit=edit,
            scores=scores,
            asr_text=asr_text,
            srt_body=srt_body,
            output_duration=output_duration,
        )
    )

    scores["r_general"] = _weighted_score(
        scores,
        config.get(
            "general_weights",
            {
                "format_compliance": 0.28,
                "source_match_fraction": 0.18,
                "video_integrity": 0.14,
                "audio_quality": 0.14,
                "edit_decision_schema": 0.09,
                "run_history_transcript_score": 0.04,
                "r_grounded_evidence_and_checks": 0.05,
                "r_anti_reward_hacking": 0.08,
            },
        ),
    )
    scores["r_hard_task"] = _weighted_score(
        scores,
        config.get(
            "hard_task_weights",
            {
                "speech_cleanup_hard": 0.28,
                "semantic_anchor_preservation": 0.24,
                "caption_hard_quality": 0.24,
                "audio_normalization": 0.13,
                "r_grounded_evidence_and_checks": 0.04,
                "r_anti_reward_hacking": 0.07,
            },
        ),
    )

    hard_cap = 1.0
    hard_cap_reasons: list[str] = []
    if fatal:
        hard_cap = 0.0
        hard_cap_reasons.append("fatal media gate failure")
    if scores["semantic_anchor_recall"] < 0.35:
        hard_cap = min(hard_cap, 0.55)
        hard_cap_reasons.append("semantic anchor recall below 0.35")
    if scores["inserted_pause_removed_ratio"] < 0.35:
        hard_cap = min(hard_cap, 0.65)
        hard_cap_reasons.append("inserted pause removal below 0.35")
    if not srt_entries:
        hard_cap = min(hard_cap, 0.75)
        hard_cap_reasons.append("missing or invalid captions.srt")
    if scores["source_match_fraction"] < 0.45:
        hard_cap = min(hard_cap, 0.35)
        hard_cap_reasons.append("source match fraction below 0.45")
    caption_cap, caption_cap_reasons = _interview_caption_layout_hard_cap(scores)
    hard_cap = min(hard_cap, caption_cap)
    hard_cap_reasons.extend(caption_cap_reasons)
    scores["interview_hard_cap_value"] = hard_cap
    scores["interview_hard_cap_applied"] = 1.0 if hard_cap < 1.0 else 0.0

    if llm_judge:
        llm_scores, llm_notes, _raw = maybe_run_llm_judge(
            task_id=task_id,
            workspace=workspace,
            hard_scores=scores,
            edit_decision=edit,
            enabled=True,
            model=llm_model,
        )
        scores.update(llm_scores)
        notes.extend(llm_notes)
    else:
        llm_scores, llm_notes, _raw = maybe_run_llm_judge(
            task_id=task_id,
            workspace=workspace,
            hard_scores=scores,
            edit_decision=edit,
            enabled=False,
            model=llm_model,
        )
        scores.update(llm_scores)
        notes.extend(llm_notes)

    scores["r_llm_proxy"] = clamp01(
        0.45 * scores["semantic_anchor_preservation"]
        + 0.25 * scores["caption_hard_quality"]
        + 0.20 * scores["speech_cleanup_hard"]
        + 0.10 * scores["r_no_face_or_subject_occlusion"]
    )
    scores["r_llm"] = (
        scores.get("llm_overall", 0.0)
        if scores.get("llm_judge_available", 0.0) >= 1.0
        else scores["r_llm_proxy"]
    )
    scores["r_llm_task"] = scores["r_llm"]
    scores["r_task"] = _weighted_score(
        scores,
        config.get("task_mix_weights", {"r_hard_task": 0.85, "r_llm": 0.15}),
    )
    final_weights = config.get("final_weights", {"r_general": 0.20, "r_task": 0.80})
    total = _weighted_score(scores, final_weights)
    scores["r_final_before_caps"] = total
    total = min(total, hard_cap)
    if llm_judge and scores.get("llm_judge_available", 0.0) < 1.0:
        scores["interview_required_llm_missing_cap"] = 0.70
        total = min(total, 0.70)
        notes.append("interview LLM judge was requested but unavailable; capped because caption layout/semantic judging depends on LLM evidence.")
    structure_cap, structure_cap_reasons = _interview_structure_hard_cap(scores)
    scores["interview_structure_hard_cap_value"] = structure_cap
    scores["interview_structure_hard_cap_applied"] = 1.0 if structure_cap < 1.0 else 0.0
    total = min(total, structure_cap)
    llm_caption_cap, llm_caption_cap_reasons = _interview_llm_caption_layout_cap(scores)
    scores["interview_llm_caption_layout_cap_value"] = llm_caption_cap
    scores["interview_llm_caption_layout_cap_applied"] = 1.0 if llm_caption_cap < 1.0 else 0.0
    total = min(total, llm_caption_cap)
    llm_quality_cap, llm_quality_cap_reasons = _interview_llm_quality_cap(scores)
    scores["interview_llm_quality_cap_value"] = llm_quality_cap
    scores["interview_llm_quality_cap_applied"] = 1.0 if llm_quality_cap < 1.0 else 0.0
    total = min(total, llm_quality_cap)
    scores["r_final_after_caps"] = total
    if hard_cap_reasons:
        notes.append(f"interview hard cap {hard_cap:.2f}: " + "; ".join(hard_cap_reasons))
    if structure_cap_reasons:
        notes.append(f"interview structure hard cap {structure_cap:.2f}: " + "; ".join(structure_cap_reasons))
    if llm_caption_cap_reasons:
        notes.append(f"interview LLM caption layout cap {llm_caption_cap:.2f}: " + "; ".join(llm_caption_cap_reasons))
    if llm_quality_cap_reasons:
        notes.append(f"interview LLM quality cap {llm_quality_cap:.2f}: " + "; ".join(llm_quality_cap_reasons))
    return ScoreRecord(run_id=run_id, task_id=task_id, agent=agent, scores=scores, total=clamp01(total), notes=_verifier_notes(notes))


def _interview_caption_layout_hard_cap(scores: dict[str, float]) -> tuple[float, list[str]]:
    cap = 1.0
    reasons: list[str] = []
    caption_detected = scores.get("caption_detected_frame_ratio", 0.0)
    face_detected = scores.get("face_detection_frame_ratio", 0.0)
    subject_detected = scores.get("subject_detection_frame_ratio", 0.0)

    if scores.get("srt_valid", 0.0) >= 1.0 and scores.get("caption_visibility", 0.0) < 0.25:
        cap = min(cap, 0.55)
        reasons.append("captions.srt exists but burned-in captions are not visibly detected")

    if caption_detected >= 0.25 and face_detected >= 0.20:
        scores["caption_layout_hard_detector_saw_face"] = 1.0

    if caption_detected >= 0.25 and subject_detected >= 0.20:
        scores["caption_layout_hard_detector_saw_subject"] = 1.0

    return cap, reasons


def _interview_evidence_and_check_scores(*, edit: dict[str, Any], scores: dict[str, float]) -> dict[str, float]:
    source_evidence = edit.get("source_evidence")
    if not isinstance(source_evidence, list):
        source_evidence = []
    evidence_items = [item for item in source_evidence if isinstance(item, dict)]
    evidence_count_score = clamp01(len(evidence_items) / 3.0)
    timecoded = 0
    text_supported = 0
    for item in evidence_items:
        has_time = any(isinstance(item.get(key), (int, float)) for key in ["source_time", "source_start", "start"])
        has_range = all(isinstance(item.get(key), (int, float)) for key in ["source_start", "source_end"])
        if has_time or has_range:
            timecoded += 1
        quote = str(item.get("quote", item.get("transcript", item.get("text", "")))).strip()
        if len(_tokens(quote)) >= 3:
            text_supported += 1
    evidence_timecode_score = clamp01(timecoded / max(1, len(evidence_items)))
    evidence_text_score = clamp01(text_supported / max(1, len(evidence_items)))

    final_checks = edit.get("final_checks")
    checks_performed = edit.get("checks_performed")
    self_checks = edit.get("self_checks")
    final_check_score = _check_field_score(final_checks)
    performed_check_score = max(_check_field_score(checks_performed), _check_field_score(self_checks))

    revision_notes = edit.get("revision_notes")
    if isinstance(revision_notes, list):
        revision_score = clamp01(sum(_present_nonempty(item) for item in revision_notes) / 1.0)
    else:
        revision_score = 0.0

    grounded = clamp01(
        0.30 * evidence_count_score
        + 0.25 * evidence_timecode_score
        + 0.20 * evidence_text_score
        + 0.15 * final_check_score
        + 0.10 * max(performed_check_score, revision_score)
    )
    return {
        "source_evidence_count_score": evidence_count_score,
        "source_evidence_timecode_score": evidence_timecode_score,
        "source_evidence_text_score": evidence_text_score,
        "final_checks_score": final_check_score,
        "checks_performed_detail_score": performed_check_score,
        "revision_notes_score": revision_score,
        "r_grounded_evidence_and_checks": grounded,
    }


def _interview_anti_reward_hack_scores(
    *,
    edit: dict[str, Any],
    scores: dict[str, float],
    asr_text: str,
    srt_body: str,
    output_duration: float,
) -> dict[str, float]:
    asr_tokens = _tokens(asr_text)
    srt_tokens = _tokens(srt_body)
    asr_density = len(asr_tokens) / max(1.0, output_duration)
    srt_density = len(srt_tokens) / max(1.0, output_duration)
    source_file_score = _source_file_constraint_score(edit)
    evidence_support = _source_evidence_quote_support_score(edit, asr_tokens=asr_tokens, srt_tokens=srt_tokens)
    caption_speech_consistency = clamp01(
        0.35 * scores.get("srt_asr_token_f1", 0.0)
        + 0.35 * scores.get("srt_asr_timed_token_f1", 0.0)
        + 0.20 * scores.get("caption_visibility", 0.0)
        + 0.10 * scores.get("srt_timing_coverage", 0.0)
    )
    if asr_tokens:
        spoken_density_score = ramp_score(asr_density, good=1.15, bad=0.50, lower_is_better=False)
    else:
        spoken_density_score = 0.65 * ramp_score(srt_density, good=1.15, bad=0.50, lower_is_better=False)

    declared_checks = max(
        _check_field_score(edit.get("final_checks")),
        _check_field_score(edit.get("checks_performed")),
        _check_field_score(edit.get("self_checks")),
    )
    actual_check_support = clamp01(
        0.18 * scores.get("duration_target_score", 0.0)
        + 0.14 * scores.get("format_compliance", 0.0)
        + 0.14 * scores.get("video_integrity", 0.0)
        + 0.14 * scores.get("audio_quality", 0.0)
        + 0.20 * caption_speech_consistency
        + 0.20 * scores.get("speech_cleanup_hard", 0.0)
    )
    verifiable_checks = declared_checks * actual_check_support
    anti_hack = clamp01(
        0.25 * source_file_score
        + 0.25 * caption_speech_consistency
        + 0.20 * evidence_support
        + 0.18 * spoken_density_score
        + 0.12 * verifiable_checks
    )
    return {
        "source_file_constraint_score": source_file_score,
        "source_evidence_quote_support_score": evidence_support,
        "caption_speech_consistency_score": caption_speech_consistency,
        "spoken_word_density": float(asr_density),
        "srt_word_density": float(srt_density),
        "spoken_content_density_score": spoken_density_score,
        "verifiable_final_checks_score": verifiable_checks,
        "r_anti_reward_hacking": anti_hack,
    }


def _source_file_constraint_score(edit: dict[str, Any]) -> float:
    files = [item.lower() for item in _as_text_list(edit.get("source_files")) if str(item).strip()]
    if not files:
        return 0.0
    text = " ".join(files)
    external_markers = [
        "http://",
        "https://",
        "youtu.be",
        "stock",
        "pexels",
        "unsplash",
        "pixabay",
        "generated",
        "synthetic",
    ]
    if any(marker in text for marker in external_markers):
        return 0.0
    allowed_markers = ["materials/source.mp4", "source.mp4", "source video", "provided source"]
    if any(marker in text for marker in allowed_markers):
        return 1.0
    return 0.5


def _source_evidence_quote_support_score(
    edit: dict[str, Any],
    *,
    asr_tokens: list[str],
    srt_tokens: list[str],
) -> float:
    evidence = edit.get("source_evidence")
    if not isinstance(evidence, list):
        return 0.0
    quote_scores: list[float] = []
    for item in evidence:
        if not isinstance(item, dict):
            continue
        quote = str(item.get("quote", item.get("transcript", item.get("text", "")))).strip()
        quote_tokens = _tokens(quote)
        if len(quote_tokens) < 3:
            continue
        asr_support = _token_window_support(quote_tokens, asr_tokens)
        srt_support = _token_window_support(quote_tokens, srt_tokens)
        quote_scores.append(max(asr_support, 0.65 * srt_support))
    if not quote_scores:
        return 0.0
    return clamp01(sum(quote_scores) / len(quote_scores))


def _token_window_support(needle: list[str], haystack: list[str]) -> float:
    if not needle or not haystack:
        return 0.0
    window_sizes = sorted({max(1, len(needle) - 2), len(needle), len(needle) + 3})
    best = _token_f1(needle, haystack)
    for size in window_sizes:
        if size >= len(haystack):
            best = max(best, _token_f1(needle, haystack))
            continue
        for start in range(0, len(haystack) - size + 1):
            best = max(best, _token_f1(needle, haystack[start : start + size]))
            if best >= 0.999:
                return 1.0
    return clamp01(best)


def _check_field_score(value: Any) -> float:
    if isinstance(value, dict):
        useful = 0
        expected = [
            "duration",
            "format",
            "audio",
            "silence",
            "captions",
            "caption_timing",
            "caption_visibility",
        ]
        lowered_keys = " ".join(str(key).lower() for key in value.keys())
        for key in expected:
            useful += int(key in lowered_keys)
        if useful == 0:
            useful = sum(_present_nonempty(item) for item in value.values())
        return clamp01(useful / 5.0)
    if isinstance(value, list):
        text = " ".join(str(item).lower() for item in value)
        expected = ["duration", "format", "audio", "silence", "caption"]
        return clamp01(sum(key in text for key in expected) / 4.0)
    return 0.0


def _interview_llm_caption_layout_cap(scores: dict[str, float]) -> tuple[float, list[str]]:
    if scores.get("llm_judge_available", 0.0) < 1.0:
        return 1.0, []
    layout = scores.get("llm_caption_visual_layout")
    if layout is None:
        return 1.0, []
    layout = float(layout)
    if layout < 0.30:
        return 0.35, ["LLM judged the burned-in captions as severely blocking faces or the interview subject"]
    if layout < 0.45:
        return 0.55, ["LLM judged the burned-in captions as visibly intrusive or poorly placed"]
    return 1.0, []


def _interview_structure_hard_cap(scores: dict[str, float]) -> tuple[float, list[str]]:
    cap = 1.0
    reasons: list[str] = []
    checks = [
        (scores.get("duration_target_score", 0.0) < 0.20, 0.78, "duration is far from the 62-72s target window"),
        (scores.get("edit_decision_schema", 0.0) < 0.80, 0.88, "edit_decision.json does not satisfy the expected schema"),
        (scores.get("semantic_anchor_recall", 0.0) < 0.75, 0.82, "hard semantic anchor recall is below 0.75"),
        (scores.get("caption_hard_quality", 0.0) < 0.55, 0.78, "hard caption quality is below 0.55"),
    ]
    for condition, value, reason in checks:
        if condition:
            cap = min(cap, value)
            reasons.append(reason)
    return cap, reasons


def _interview_llm_quality_cap(scores: dict[str, float]) -> tuple[float, list[str]]:
    if scores.get("llm_judge_available", 0.0) < 1.0:
        return 1.0, []
    cap = 1.0
    reasons: list[str] = []
    checks = [
        (scores.get("llm_semantic_completion", 1.0) < 0.60, 0.75, "LLM semantic completion below 0.60"),
        (scores.get("llm_caption_text_accuracy_sync", 1.0) < 0.60, 0.75, "LLM caption text/timing accuracy below 0.60"),
        (scores.get("llm_meaning_order_preservation", 1.0) < 0.55, 0.78, "LLM meaning/order preservation below 0.55"),
        (scores.get("llm_publishability", 1.0) < 0.50, 0.72, "LLM publishability below 0.50"),
    ]
    for condition, value, reason in checks:
        if condition:
            cap = min(cap, value)
            reasons.append(reason)
    return cap, reasons


def _format_score(scores: dict[str, float]) -> float:
    return clamp01(
        0.35 * scores.get("duration_target_score", 0.0)
        + 0.25 * scores.get("aspect_score", 0.0)
        + 0.20 * scores.get("resolution_score", 0.0)
        + 0.10 * scores.get("video_codec_score", 0.0)
        + 0.10 * scores.get("audio_codec_score", 0.0)
    )


def _history_artifact_scores(workspace: Path) -> dict[str, float]:
    run_history = workspace / "submit" / "run_history.md"
    agent_transcript = workspace / "submit" / "agent_transcript.md"
    history_ok = run_history.exists() and run_history.stat().st_size >= 80
    transcript_ok = agent_transcript.exists() and agent_transcript.stat().st_size >= 80
    return {
        "run_history_exists": 1.0 if history_ok else 0.0,
        "agent_transcript_exists": 1.0 if transcript_ok else 0.0,
        "run_history_transcript_score": (float(history_ok) + float(transcript_ok)) / 2.0,
    }


def _caption_text(edit: dict[str, Any]) -> str:
    texts: list[str] = []
    captions = edit.get("captions")
    if isinstance(captions, list):
        for item in captions:
            if isinstance(item, dict):
                texts.append(str(item.get("text", "")))
            else:
                texts.append(str(item))
    return " ".join(texts).lower()


def _srt_asr_alignment_scores(*, srt_entries: list[dict[str, Any]], asr_data: dict[str, Any] | None) -> dict[str, float]:
    if not srt_entries or not asr_data:
        return {
            "srt_asr_token_f1": 0.0,
            "srt_asr_timed_token_f1": 0.0,
            "srt_asr_timed_cue_coverage": 0.0,
        }
    srt_tokens = _tokens(srt_text(srt_entries))
    asr_text = str(asr_data.get("text", ""))
    asr_tokens = _tokens(asr_text)
    token_f1 = _token_f1(srt_tokens, asr_tokens)

    words: list[dict[str, Any]] = []
    for segment in asr_data.get("segments", []) if isinstance(asr_data.get("segments"), list) else []:
        for word in segment.get("words", []) if isinstance(segment.get("words"), list) else []:
            if not isinstance(word, dict):
                continue
            token = _tokens(str(word.get("word", "")))
            if not token:
                continue
            start = word.get("start")
            end = word.get("end")
            if isinstance(start, (int, float)) and isinstance(end, (int, float)):
                words.append({"token": token[0], "start": float(start), "end": float(end)})

    if not words:
        return {
            "srt_asr_token_f1": token_f1,
            "srt_asr_timed_token_f1": token_f1 * 0.5,
            "srt_asr_timed_cue_coverage": 0.0,
        }

    weighted_f1 = 0.0
    total_weight = 0.0
    checked = 0
    for entry in srt_entries:
        cue_tokens = _tokens(str(entry.get("text", "")))
        if not cue_tokens:
            continue
        start = float(entry.get("start", 0.0))
        end = float(entry.get("end", 0.0))
        window_tokens = [
            word["token"]
            for word in words
            if start - 0.20 <= (word["start"] + word["end"]) / 2.0 <= end + 0.20
        ]
        weight = len(cue_tokens)
        weighted_f1 += weight * _token_f1(cue_tokens, window_tokens)
        total_weight += weight
        checked += 1

    timed_f1 = weighted_f1 / max(1.0, total_weight)
    cue_coverage = checked / max(1, len(srt_entries))
    return {
        "srt_asr_token_f1": clamp01(token_f1),
        "srt_asr_timed_token_f1": clamp01(timed_f1),
        "srt_asr_timed_cue_coverage": clamp01(cue_coverage),
    }


def _token_f1(left: list[str], right: list[str]) -> float:
    if not left or not right:
        return 0.0
    right_counts: dict[str, int] = {}
    for token in right:
        right_counts[token] = right_counts.get(token, 0) + 1
    overlap = 0
    for token in left:
        count = right_counts.get(token, 0)
        if count <= 0:
            continue
        overlap += 1
        right_counts[token] = count - 1
    precision = overlap / len(left)
    recall = overlap / len(right)
    if precision + recall <= 0:
        return 0.0
    return clamp01(2 * precision * recall / (precision + recall))


def _caption_cue_times(edit: dict[str, Any]) -> list[float]:
    cue_times: list[float] = []
    captions = edit.get("captions")
    if not isinstance(captions, list):
        return cue_times
    for item in captions:
        if not isinstance(item, dict):
            continue
        start = item.get("start", item.get("output_start"))
        end = item.get("end", item.get("output_end"))
        if isinstance(start, (int, float)) and isinstance(end, (int, float)):
            cue_times.append((float(start) + float(end)) / 2.0)
        elif isinstance(start, (int, float)):
            cue_times.append(float(start) + 0.5)
    return cue_times


def _edit_media_consistency_score(ranges: list[tuple[float, float]], matches: list[Any]) -> float:
    if not ranges:
        return 0.0
    if not matches:
        return 0.0
    hits = 0
    for match in matches:
        if any(start <= match.source_time <= end for start, end in ranges):
            hits += 1
    return clamp01(hits / max(1, len(matches)))


def _semantic_anchor_scores(anchors: list[dict[str, Any]], text: str) -> dict[str, float]:
    if not anchors:
        return {
            "semantic_anchor_recall": 0.0,
            "semantic_anchor_order": 0.0,
            "semantic_anchor_diversity": 0.0,
        }
    lowered = text.lower()
    hits = 0
    positions: list[int] = []
    for anchor in anchors:
        phrase_positions = [
            lowered.find(str(phrase).lower())
            for phrase in anchor.get("phrases", anchor.get("required_phrases", []))
            if str(phrase).strip()
        ]
        phrase_positions = [position for position in phrase_positions if position >= 0]
        if phrase_positions:
            hits += 1
            positions.append(min(phrase_positions))
    recall = hits / len(anchors)
    if len(positions) < 2:
        order = 1.0 if positions else 0.0
    else:
        inversions = sum(1 for left, right in zip(positions, positions[1:]) if right < left)
        order = 1.0 - inversions / max(1, len(positions) - 1)
    return {
        "semantic_anchor_recall": clamp01(recall),
        "semantic_anchor_order": clamp01(order),
        "semantic_anchor_diversity": clamp01(hits / len(anchors)),
    }


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9']+", text.lower())


def _duplicate_ngram_rate(tokens: list[str], *, n: int = 3) -> float:
    if len(tokens) < n * 2:
        return 0.0
    ngrams = [tuple(tokens[idx : idx + n]) for idx in range(len(tokens) - n + 1)]
    if not ngrams:
        return 0.0
    unique = len(set(ngrams))
    return clamp01(1.0 - unique / len(ngrams))


def _interview_defect_public_intervals(*, repo: Path, task_id: str, ground_truth: dict[str, Any]) -> list[dict[str, Any]]:
    timeline_path = repo / "tasks" / task_id / "private" / "public_timeline.json"
    timeline = load_json_if_exists(timeline_path)
    if timeline.get("defect_public_intervals"):
        return [
            {
                "kind": str(item["kind"]),
                "public_start": float(item["public_start"]),
                "public_end": float(item["public_end"]),
            }
            for item in timeline["defect_public_intervals"]
        ]

    defects: list[dict[str, Any]] = []
    events: list[tuple[float, str, dict[str, Any]]] = []
    for item in ground_truth["defect_map"]["inserted_dead_air"]:
        events.append((float(item["clean_time_sec"]), "inserted_dead_air", item))
    for item in ground_truth["defect_map"]["repeated_phrase_loops"]:
        events.append((float(item["clean_start_sec"]), "repeated_phrase_loop", item))
    events.sort(key=lambda item: item[0])

    cumulative_extra = 0.0
    for _, kind, item in events:
        if kind == "inserted_dead_air":
            clean_time = float(item["clean_time_sec"])
            duration = float(item["duration_sec"])
            public_start = clean_time + cumulative_extra
            defects.append({"kind": kind, "public_start": public_start, "public_end": public_start + duration})
            cumulative_extra += duration
        else:
            start = float(item["clean_start_sec"])
            end = float(item["clean_end_sec"])
            duration = end - start
            repeats = max(0, int(item.get("repeat_count", 2)) - 1)
            public_original_start = start + cumulative_extra
            for repeat_idx in range(repeats):
                public_start = public_original_start + duration * (repeat_idx + 1)
                defects.append({"kind": kind, "public_start": public_start, "public_end": public_start + duration})
            cumulative_extra += duration * repeats
    return defects


def _apply_llm(
    task_id: str,
    workspace: Path,
    scores: dict[str, float],
    edit: dict[str, Any],
    total: float,
    notes: list[str],
    *,
    enabled: bool,
    model: str | None,
) -> tuple[float, list[str]]:
    llm_scores, llm_notes, _raw = maybe_run_llm_judge(
        task_id=task_id,
        workspace=workspace,
        hard_scores=scores,
        edit_decision=edit,
        enabled=enabled,
        model=model,
    )
    scores.update(llm_scores)
    notes.extend(llm_notes)
    if llm_scores.get("llm_judge_available", 0.0) >= 1.0:
        if task_id == "rough_interview_caption_cleanup":
            total = 0.75 * total + 0.25 * llm_scores.get("llm_overall", 0.0)
        else:
            total = 0.80 * total + 0.20 * llm_scores.get("llm_overall", 0.0)
    return total, notes


def _verifier_notes(notes: list[str]) -> list[str]:
    out = list(notes)
    out.append(
        "v1 verifier: media gates and CPU visual/audio matching are implemented; ROI and semantic checks remain heuristic unless LLM judge/ASR evidence is enabled."
    )
    return out
