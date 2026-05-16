from __future__ import annotations

from pathlib import Path
from typing import Any

from ..media.audio import audio_quality_score, audio_stats
from ..media.ffprobe import probe
from ..media.video import video_integrity_score, video_stats
from ..schema import ScoreRecord
from ..tasks.registry import get_task_definition
from .basic import basic_submission_score
from .common import (
    aspect_score,
    clamp01,
    extract_local_shifts,
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


def score_task_submission(
    *,
    run_id: str,
    task_id: str,
    agent: str,
    workspace: Path,
    repo: Path,
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
        return _score_pancake(run_id, task_id, agent, workspace, ground_truth, config, schema)
    if task_id == "piecewise_av_sync_repair":
        return _score_piecewise_sync(run_id, task_id, agent, workspace, ground_truth, config, schema)
    if task_id == "rough_interview_caption_cleanup":
        return _score_interview(run_id, task_id, agent, workspace, ground_truth, config, schema)
    return basic_submission_score(run_id=run_id, task_id=task_id, agent=agent, workspace=workspace)


def _media_context(workspace: Path, config: dict[str, Any]) -> tuple[dict[str, float], dict[str, Any], list[str], bool]:
    notes: list[str] = []
    output = workspace / "submit" / "output.mp4"
    source = workspace / "materials" / "source.mp4"
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
    context: dict[str, Any] = {}
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
    ground_truth: dict[str, Any],
    config: dict[str, Any],
    schema: dict[str, Any],
) -> ScoreRecord:
    scores, context, notes, fatal = _media_context(workspace, config)
    edit_score, edit, edit_notes = validate_json(workspace / "submit" / "edit_decision.json", schema)
    notes.extend(edit_notes)
    scores["edit_decision_schema"] = edit_score

    ranges = extract_source_ranges(edit)
    total_declared = sum(end - start for start, end in ranges)
    scores["declared_source_range_count"] = float(len(ranges))
    scores["hard_2_source_authenticity_timeline"] = clamp01(0.55 * min(1.0, total_declared / max(1.0, context.get("duration", 60.0))) + 0.45 * min(1.0, len(ranges) / 4.0))

    step_scores: list[float] = []
    first_hits: list[float] = []
    caption_text = _caption_text(edit)
    for step in ground_truth["required_steps"]:
        interval = tuple(float(x) for x in step["interval"])
        covered = total_overlap(ranges, interval)
        visual = ramp_score(covered, good=2.5, bad=0.0, lower_is_better=False)
        keywords = step.get("keywords", [])
        keyword_score = 1.0 if any(str(keyword).lower() in caption_text for keyword in keywords) else 0.0
        step_scores.append(0.8 * visual + 0.2 * keyword_score)
        hits = [max(start, interval[0]) for start, end in ranges if interval_overlap((start, end), interval) > 0]
        if hits:
            first_hits.append(min(hits))
    order_score = 1.0 if first_hits == sorted(first_hits) and len(first_hits) >= 4 else 0.7 if len(first_hits) >= 3 else 0.35
    scores["hard_3_expert_step_coverage_order"] = clamp01((sum(step_scores) / max(1, len(step_scores))) * order_score)

    negative_leak = 0.0
    for item in ground_truth["negative_intervals"]:
        negative_leak += total_overlap(ranges, tuple(float(x) for x in item["interval"]))
    scores["negative_leak_seconds_declared"] = negative_leak
    scores["hard_4_negative_material_suppression"] = ramp_score(negative_leak, good=4.0, bad=18.0, lower_is_better=True)

    caption_count = len(edit.get("captions", [])) if isinstance(edit.get("captions"), list) else 0
    caption_keyword_score = sum(1 for step in ground_truth["required_steps"] if any(k in caption_text for k in step.get("keywords", []))) / len(ground_truth["required_steps"])
    scores["hard_5_vertical_roi_caption"] = clamp01(0.35 * min(1.0, caption_count / 5.0) + 0.35 * caption_keyword_score + 0.30 * scores.get("video_integrity", 0.0))

    scores["hard_1_format_duration"] = _format_score(scores)
    scores["hard_6_audio_quality_cut_smoothness"] = scores.get("audio_quality", 0.0)
    scores["metadata"] = edit_score

    weights = config["weights"]
    total = sum(scores.get(key, 0.0) * weight for key, weight in weights.items())
    if fatal:
        total = 0.0
    if scores["hard_4_negative_material_suppression"] < 0.30:
        total = min(total, 0.55)
    if scores["hard_3_expert_step_coverage_order"] < 0.40:
        total = min(total, 0.60)
    return ScoreRecord(run_id=run_id, task_id=task_id, agent=agent, scores=scores, total=clamp01(total), notes=_v0_notes(notes))


def _score_piecewise_sync(
    run_id: str,
    task_id: str,
    agent: str,
    workspace: Path,
    ground_truth: dict[str, Any],
    config: dict[str, Any],
    schema: dict[str, Any],
) -> ScoreRecord:
    scores, context, notes, fatal = _media_context(workspace, config)
    edit_score, edit, edit_notes = validate_json(workspace / "submit" / "edit_decision.json", schema)
    notes.extend(edit_notes)
    scores["edit_decision_schema"] = edit_score

    shifts = extract_local_shifts(edit)
    recipe_offsets = ground_truth["corruption_recipe"]["piecewise_audio_offsets"]
    residuals: list[float] = []
    for zone in recipe_offsets:
        expected_repair = -float(zone["audio_delay_ms"])
        overlap_scores: list[tuple[float, float]] = []
        zone_interval = (float(zone["clean_start_sec"]), float(zone["clean_end_sec"]))
        for shift in shifts:
            overlap = interval_overlap((shift["source_start"], shift["source_end"]), zone_interval)
            if overlap > 0:
                overlap_scores.append((overlap, abs(float(shift["shift_ms"]) - expected_repair)))
        if overlap_scores:
            residuals.append(min(overlap_scores, key=lambda item: item[1])[1])
        else:
            residuals.append(999.0)
    if residuals:
        median_residual = sorted(residuals)[len(residuals) // 2]
        p90_residual = sorted(residuals)[min(len(residuals) - 1, int(round(0.9 * (len(residuals) - 1))))]
    else:
        median_residual = p90_residual = 999.0
    scores["declared_sync_median_residual_ms"] = float(median_residual)
    scores["declared_sync_p90_residual_ms"] = float(p90_residual)
    sync_score = 0.65 * ramp_score(median_residual, good=80.0, bad=420.0) + 0.35 * ramp_score(p90_residual, good=120.0, bad=560.0)
    distinct_shifts = len({round(float(item.get("shift_ms", 0.0)) / 50.0) for item in shifts})
    scores["local_av_sync_repair"] = clamp01(sync_score * min(1.0, distinct_shifts / 2.0))

    ranges = extract_source_ranges(edit)
    required_scores: list[float] = []
    for span in ground_truth["required_spans"]:
        interval = tuple(float(x) for x in span["interval"])
        duration = interval[1] - interval[0]
        required_scores.append(clamp01(total_overlap(ranges, interval) / max(1.0, duration * 0.85)))
    scores["required_span_coverage"] = sum(required_scores) / max(1, len(required_scores))
    scores["source_time_monotonicity"] = monotonicity_score(ranges)
    vstats = context.get("video_stats", {})
    astats = context.get("audio_stats", {})
    damage_cleanup = min(
        scores.get("video_integrity", 0.0),
        ramp_score(float(vstats.get("black_frame_ratio", 0.0)), good=0.005, bad=0.08),
        ramp_score(float(vstats.get("max_frozen_run_sec", 0.0)), good=0.5, bad=4.0),
        ramp_score(float(astats.get("max_silence_sec", 0.0)), good=1.2, bad=4.0),
    )
    scores["damage_cleanup"] = damage_cleanup
    scores["content_preservation_damage_cleanup"] = clamp01(
        0.45 * scores["required_span_coverage"] + 0.20 * scores["source_time_monotonicity"] + 0.35 * damage_cleanup
    )

    scores["format_compliance"] = _format_score(scores)
    scores["deliverable_quality_explainability"] = clamp01(
        0.45 * scores["format_compliance"] + 0.30 * scores.get("audio_quality", 0.0) + 0.25 * edit_score
    )
    total = (
        config["weights"]["local_av_sync_repair"] * scores["local_av_sync_repair"]
        + config["weights"]["content_preservation_damage_cleanup"] * scores["content_preservation_damage_cleanup"]
        + config["weights"]["deliverable_quality_explainability"] * scores["deliverable_quality_explainability"]
    )
    if fatal:
        total = 0.0
    if scores["local_av_sync_repair"] < 0.35:
        total = min(total, 0.55)
    if scores["required_span_coverage"] < 0.45:
        total = min(total, 0.60)
    return ScoreRecord(run_id=run_id, task_id=task_id, agent=agent, scores=scores, total=clamp01(total), notes=_v0_notes(notes))


def _score_interview(
    run_id: str,
    task_id: str,
    agent: str,
    workspace: Path,
    ground_truth: dict[str, Any],
    config: dict[str, Any],
    schema: dict[str, Any],
) -> ScoreRecord:
    scores, context, notes, fatal = _media_context(workspace, config)
    edit_score, edit, edit_notes = validate_json(workspace / "submit" / "edit_decision.json", schema)
    notes.extend(edit_notes)
    scores["edit_decision_schema"] = edit_score
    removed = extract_removed_ranges(edit)

    dead_air_scores: list[float] = []
    for item in ground_truth["defect_map"]["inserted_dead_air"]:
        t = float(item["clean_time_sec"])
        dur = float(item["duration_sec"])
        dead_air_scores.append(clamp01(total_overlap(removed, (t, t + dur)) / dur))
    repeat_scores: list[float] = []
    for item in ground_truth["defect_map"]["repeated_phrase_loops"]:
        interval = (float(item["clean_start_sec"]), float(item["clean_end_sec"]))
        repeat_scores.append(1.0 if total_overlap(removed, interval) > 0.5 else 0.0)
    scores["inserted_pause_removed_ratio"] = sum(dead_air_scores) / max(1, len(dead_air_scores))
    scores["repeat_loop_suppression"] = sum(repeat_scores) / max(1, len(repeat_scores))

    srt_entries = parse_srt(workspace / "submit" / "captions.srt")
    srt_body = srt_text(srt_entries)
    combined_text = f"{srt_body} {_caption_text(edit)} {edit}".lower()
    anchor_hits = []
    for anchor in ground_truth["semantic_anchors"]:
        anchor_hits.append(1.0 if any(str(phrase).lower() in combined_text for phrase in anchor["phrases"]) else 0.0)
    scores["semantic_anchor_recall"] = sum(anchor_hits) / max(1, len(anchor_hits))
    scores["speech_cleanup_semantic_preservation"] = clamp01(
        0.40 * scores["inserted_pause_removed_ratio"]
        + 0.25 * scores["repeat_loop_suppression"]
        + 0.35 * scores["semantic_anchor_recall"]
    )

    scores["srt_valid"] = 1.0 if srt_entries else 0.0
    caption_duration = sum(max(0.0, float(entry["end"]) - float(entry["start"])) for entry in srt_entries)
    output_duration = max(1.0, float(context.get("duration", 1.0)))
    scores["srt_timing_coverage"] = clamp01(caption_duration / (output_duration * 0.70))
    scores["caption_audio_deliverable_quality"] = clamp01(
        0.30 * scores["srt_valid"]
        + 0.25 * scores["srt_timing_coverage"]
        + 0.20 * (1.0 if len(srt_body.split()) >= 80 else len(srt_body.split()) / 80.0)
        + 0.25 * scores.get("audio_quality", 0.0)
    )

    ranges = extract_source_ranges(edit)
    scores["source_fidelity_format_naturalness"] = clamp01(
        0.35 * _format_score(scores)
        + 0.25 * min(1.0, len(ranges) / 3.0)
        + 0.20 * scores.get("video_integrity", 0.0)
        + 0.20 * edit_score
    )
    total = (
        config["weights"]["speech_cleanup_semantic_preservation"] * scores["speech_cleanup_semantic_preservation"]
        + config["weights"]["caption_audio_deliverable_quality"] * scores["caption_audio_deliverable_quality"]
        + config["weights"]["source_fidelity_format_naturalness"] * scores["source_fidelity_format_naturalness"]
    )
    if fatal:
        total = 0.0
    if scores["semantic_anchor_recall"] < 0.35:
        total = min(total, 0.55)
    if scores["inserted_pause_removed_ratio"] < 0.35:
        total = min(total, 0.65)
    if not srt_entries:
        total = min(total, 0.75)
    return ScoreRecord(run_id=run_id, task_id=task_id, agent=agent, scores=scores, total=clamp01(total), notes=_v0_notes(notes))


def _format_score(scores: dict[str, float]) -> float:
    return clamp01(
        0.35 * scores.get("duration_target_score", 0.0)
        + 0.25 * scores.get("aspect_score", 0.0)
        + 0.20 * scores.get("resolution_score", 0.0)
        + 0.10 * scores.get("video_codec_score", 0.0)
        + 0.10 * scores.get("audio_codec_score", 0.0)
    )


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


def _v0_notes(notes: list[str]) -> list[str]:
    out = list(notes)
    out.append(
        "v0 verifier: private media matching is not implemented yet; interval/sync coverage currently uses edit_decision declarations plus hard media gates."
    )
    return out
