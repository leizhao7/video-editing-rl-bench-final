from __future__ import annotations

from pathlib import Path
from typing import Any
import re

from ..media.audio import audio_quality_score, audio_stats
from ..media.captions import burned_caption_visibility_score
from ..media.ffprobe import probe
from ..media.matching import (
    match_video_timeline,
    matched_fraction,
    seconds_in_intervals,
    sync_residuals_ms,
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
    matches = match_video_timeline(output=output, source=source, output_fps=1.0, source_fps=1.0)
    if not matches:
        notes.append("visual source matching unavailable or found no confident matches")
    source_match_fraction = matched_fraction(matches, output_duration=float(context.get("duration", 0.0)), sample_step_sec=1.0)
    diversity = timeline_diversity(matches)
    scores["source_match_fraction"] = source_match_fraction
    scores["source_timeline_diversity"] = float(diversity)
    scores["source_time_monotonicity"] = timeline_monotonicity(matches)
    scores["hard_2_source_authenticity_timeline"] = clamp01(
        0.70 * source_match_fraction
        + 0.20 * min(1.0, diversity / 4.0)
        + 0.10 * scores["source_time_monotonicity"]
    )

    step_scores: list[float] = []
    first_hits: list[float] = []
    caption_text = _caption_text(edit)
    for step in ground_truth["required_steps"]:
        interval = tuple(float(x) for x in step["interval"])
        covered = seconds_in_intervals(matches, [interval], sample_step_sec=1.0)
        visual = ramp_score(covered, good=2.5, bad=0.0, lower_is_better=False)
        keywords = step.get("keywords", [])
        keyword_score = 1.0 if any(str(keyword).lower() in caption_text for keyword in keywords) else 0.0
        step_scores.append(0.8 * visual + 0.2 * keyword_score)
        hits = [match.source_time for match in matches if interval[0] <= match.source_time <= interval[1]]
        if hits:
            first_hits.append(min(hits))
    order_score = 1.0 if first_hits == sorted(first_hits) and len(first_hits) >= 4 else 0.7 if len(first_hits) >= 3 else 0.35
    scores["hard_3_expert_step_coverage_order"] = clamp01((sum(step_scores) / max(1, len(step_scores))) * order_score)

    negative_leak = 0.0
    for item in ground_truth["negative_intervals"]:
        negative_leak += seconds_in_intervals(matches, [tuple(float(x) for x in item["interval"])], sample_step_sec=1.0)
    scores["negative_leak_seconds"] = negative_leak
    scores["hard_4_negative_material_suppression"] = ramp_score(negative_leak, good=4.0, bad=18.0, lower_is_better=True)

    caption_count = len(edit.get("captions", [])) if isinstance(edit.get("captions"), list) else 0
    caption_keyword_score = sum(1 for step in ground_truth["required_steps"] if any(k in caption_text for k in step.get("keywords", []))) / len(ground_truth["required_steps"])
    cue_times = _caption_cue_times(edit)
    caption_visibility = burned_caption_visibility_score(output, cue_times)
    border_score = 1.0 - float(context.get("video_stats", {}).get("border_black_fraction", 0.0))
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
    scores["caption_visibility"] = caption_visibility
    scores["hard_5_vertical_roi_caption"] = clamp01(
        0.20 * min(1.0, caption_count / 5.0)
        + 0.20 * caption_keyword_score
        + 0.20 * caption_visibility
        + 0.40 * roi_score
    )

    scores["hard_1_format_duration"] = _format_score(scores)
    scores["hard_6_audio_quality_cut_smoothness"] = scores.get("audio_quality", 0.0)
    scores["metadata"] = clamp01(
        0.50 * edit_score
        + 0.30 * _edit_media_consistency_score(extract_source_ranges(edit), matches)
        + 0.20 * scores.get("run_history_transcript_score", 0.0)
    )

    weights = config["weights"]
    total = sum(scores.get(key, 0.0) * weight for key, weight in weights.items())
    if fatal:
        total = 0.0
    if scores["hard_2_source_authenticity_timeline"] < 0.50:
        total = min(total, 0.40)
    if scores["hard_4_negative_material_suppression"] < 0.30:
        total = min(total, 0.55)
    if scores["hard_3_expert_step_coverage_order"] < 0.40:
        total = min(total, 0.60)
    total, notes = _apply_llm(task_id, workspace, scores, edit, total, notes, enabled=llm_judge, model=llm_model)
    return ScoreRecord(run_id=run_id, task_id=task_id, agent=agent, scores=scores, total=clamp01(total), notes=_verifier_notes(notes))


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
    scores, context, notes, fatal = _media_context(workspace, config)
    edit_score, edit, edit_notes = validate_json(workspace / "submit" / "edit_decision.json", schema)
    notes.extend(edit_notes)
    scores["edit_decision_schema"] = edit_score

    output = Path(context["output_path"])
    clean_reference = repo / "tasks" / task_id / "private" / "clean_reference.mp4"
    if not clean_reference.exists():
        notes.append("missing private/clean_reference.mp4; full A/V residual verifier cannot run")
        residuals = []
        clean_reference = Path(context["source_path"])
    else:
        residuals = [abs(value) for value in sync_residuals_ms(output=output, clean_reference=clean_reference)]
    if residuals:
        median_residual = sorted(residuals)[len(residuals) // 2]
        p90_residual = sorted(residuals)[min(len(residuals) - 1, int(round(0.9 * (len(residuals) - 1))))]
    else:
        median_residual = p90_residual = 999.0
    scores["sync_median_residual_ms"] = float(median_residual)
    scores["sync_p90_residual_ms"] = float(p90_residual)
    scores["sync_anchor_match_coverage"] = min(1.0, len(residuals) / 12.0)
    sync_score = 0.65 * ramp_score(median_residual, good=80.0, bad=420.0) + 0.35 * ramp_score(p90_residual, good=120.0, bad=560.0)
    scores["local_av_sync_repair"] = clamp01(sync_score * scores["sync_anchor_match_coverage"])

    video_matches = match_video_timeline(output=output, source=clean_reference, output_fps=1.0, source_fps=1.0, threshold=0.55)
    if not video_matches:
        notes.append("clean-reference visual matching found no confident matches")
    required_scores: list[float] = []
    for span in ground_truth["required_spans"]:
        interval = tuple(float(x) for x in span["interval"])
        duration = interval[1] - interval[0]
        covered = seconds_in_intervals(video_matches, [interval], sample_step_sec=1.0)
        required_scores.append(clamp01(covered / max(1.0, duration * 0.75)))
    scores["required_span_coverage"] = sum(required_scores) / max(1, len(required_scores))
    scores["source_time_monotonicity"] = timeline_monotonicity(video_matches)
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
        0.40 * scores["format_compliance"]
        + 0.25 * scores.get("audio_quality", 0.0)
        + 0.20 * edit_score
        + 0.15 * scores.get("run_history_transcript_score", 0.0)
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
    total, notes = _apply_llm(task_id, workspace, scores, edit, total, notes, enabled=llm_judge, model=llm_model)
    return ScoreRecord(run_id=run_id, task_id=task_id, agent=agent, scores=scores, total=clamp01(total), notes=_verifier_notes(notes))


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
    scores["speech_cleanup_semantic_preservation"] = clamp01(
        0.30 * scores["inserted_pause_removed_ratio"]
        + 0.20 * scores["repeat_loop_suppression"]
        + 0.30 * scores["semantic_anchor_recall"]
        + 0.10 * scores["semantic_anchor_order"]
        + 0.10 * (1.0 - scores["duplicate_ngram_rate"])
    )

    scores["srt_valid"] = 1.0 if srt_entries else 0.0
    caption_duration = sum(max(0.0, float(entry["end"]) - float(entry["start"])) for entry in srt_entries)
    output_duration = max(1.0, float(context.get("duration", 1.0)))
    cue_times = [(float(entry["start"]) + float(entry["end"])) / 2.0 for entry in srt_entries[:20]]
    scores["caption_visibility"] = burned_caption_visibility_score(output, cue_times)
    scores["srt_timing_coverage"] = clamp01(caption_duration / (output_duration * 0.70))
    scores["caption_audio_deliverable_quality"] = clamp01(
        0.22 * scores["srt_valid"]
        + 0.22 * scores["srt_timing_coverage"]
        + 0.18 * (1.0 if len(srt_body.split()) >= 80 else len(srt_body.split()) / 80.0)
        + 0.18 * scores["caption_visibility"]
        + 0.20 * scores.get("audio_quality", 0.0)
    )

    scores["source_fidelity_format_naturalness"] = clamp01(
        0.30 * _format_score(scores)
        + 0.22 * scores["source_match_fraction"]
        + 0.18 * scores.get("video_integrity", 0.0)
        + 0.20 * edit_score
        + 0.10 * scores.get("run_history_transcript_score", 0.0)
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
    if scores["source_match_fraction"] < 0.45:
        total = min(total, 0.35)
    total, notes = _apply_llm(task_id, workspace, scores, edit, total, notes, enabled=llm_judge, model=llm_model)
    return ScoreRecord(run_id=run_id, task_id=task_id, agent=agent, scores=scores, total=clamp01(total), notes=_verifier_notes(notes))


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
        total = 0.80 * total + 0.20 * llm_scores.get("llm_overall", 0.0)
    return total, notes


def _verifier_notes(notes: list[str]) -> list[str]:
    out = list(notes)
    out.append(
        "v1 verifier: media gates and CPU visual/audio matching are implemented; ROI and semantic checks remain heuristic unless LLM judge/ASR evidence is enabled."
    )
    return out
