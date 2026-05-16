from __future__ import annotations

from typing import Any

from .base import TaskDefinition


def _base_schema(required_extra: list[str], properties_extra: dict[str, Any]) -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "additionalProperties": True,
        "required": ["source_files", "tools_used", "self_checks", *required_extra],
        "properties": {
            "source_files": {"type": "array", "items": {"type": "string"}, "minItems": 1},
            "tools_used": {"type": "array", "items": {"type": "string"}},
            "self_checks": {"type": "object", "additionalProperties": True},
            **properties_extra,
        },
    }


_range_schema = {
    "type": "object",
    "required": ["source_start", "source_end"],
    "properties": {
        "source_start": {"type": "number", "minimum": 0},
        "source_end": {"type": "number", "minimum": 0},
        "output_start": {"type": "number", "minimum": 0},
        "output_end": {"type": "number", "minimum": 0},
        "reason": {"type": "string"},
        "label": {"type": "string"},
    },
    "additionalProperties": True,
}


PANCAKE_PROMPT = """# Task: Expert Pancake Tutorial Extraction

You are given `materials/source.mp4`, a landscape "50 People Try" pancake challenge video.

Create a 55-65 second vertical social tutorial that feels like a standalone pancake recipe short.

Use the expert/proficient pancake-making sequence. Do not build the edit around the novice blooper
montage, failed attempts, jokes, end cards, or unrelated banter.

The final story must show these recipe steps in order:
1. grease the pan with butter,
2. pour or swirl the batter,
3. wait for bubbles as the doneness cue,
4. flip with a spatula,
5. plate and finish the pancake.

Requirements:
- Export `submit/output.mp4` as portrait 9:16 H.264/AAC, preferably 1080x1920 or 720x1280.
- Keep pan, pancake, hands, spatula, and plated result visible in the vertical frame.
- Add short burned-in captions for each recipe step.
- Keep useful original cooking/speech audio, normalize loudness, and avoid clipping or silent padding.
- Do not add external footage, unrelated music, synthetic narration, or generated visuals.
- Write `submit/edit_decision.json` with source ranges, output ranges, crop decisions, caption
  text/timing, audio adjustments, and measured self-checks.
- Write `submit/run_history.md` and `submit/agent_transcript.md` with your action log and
  observable work transcript/summary.
"""


PIECEWISE_SYNC_PROMPT = """# Task: Piecewise A/V Sync and Damage Repair

You are given `materials/source.mp4`, a damaged 16:9 tutorial excerpt from a creator.

The clip has multiple technical defects:
- audio/video sync is wrong by different amounts in different parts of the clip;
- there is black leader and black tail;
- there is one accidental freeze/dead-air splice;
- speech loudness is uneven and there may be mild hum/noise.

Create:
- `submit/output.mp4`
- `submit/edit_decision.json`
- `submit/run_history.md`
- `submit/agent_transcript.md`

Requirements:
1. Repair A/V sync locally. Do not assume a single global audio offset is enough.
2. Remove black leader/tail and the accidental freeze/dead-air splice.
3. Preserve the useful tutorial content in original order, including the clap demonstration and the
   explanation of why creators clap before takes.
4. Keep natural pacing. Do not delete explanation just to make sync easier.
5. Normalize speech loudness without clipping, muting, or replacing the original audio.
6. Export a standard landscape MP4: H.264 video, AAC audio, 1280x720, square pixels, 24-30 fps,
   duration 88-98 seconds.
7. Do not add external footage, synthetic speech, unrelated music, large overlays, or face-covering text.
8. Write `submit/edit_decision.json` with segment cuts, estimated local audio shifts, removed damage
   ranges, filters used, and measured self-checks.
9. Write `submit/run_history.md` and `submit/agent_transcript.md` with your action log and
   observable work transcript/summary.
"""


INTERVIEW_PROMPT = """# Task: Rough Interview Cleanup and Captioning

You are editing a rough interview excerpt into a polished educational social clip.

Input:
- `materials/source.mp4` is a rough 16:9 interview excerpt.

Create:
- `submit/output.mp4`
- `submit/captions.srt`
- `submit/edit_decision.json`
- `submit/run_history.md`
- `submit/agent_transcript.md`

Output requirements:
- 60-75 seconds total duration.
- 1280x720, 16:9, H.264 video with AAC audio.
- Preserve a clear self-contained explanation about helping young people stay motivated and thrive at work.
- Remove long dead air, obvious false starts, and repeated phrase loops while keeping speech natural.
- Keep the main speaker's meaning intact. Do not reorder ideas in a way that changes the argument.
- Normalize spoken audio so it is comfortably listenable without clipping or pumping.
- Add readable burned-in captions for all spoken words, and save the timing as `submit/captions.srt`.
- Avoid black frames, frozen frames, unrelated footage, background music, synthetic narration, and heavy decorative overlays.

In `submit/edit_decision.json`, list kept source segments, removed defects or pauses, audio filters,
subtitle generation method, caption style, and measured self-checks.

Also write `submit/run_history.md` and `submit/agent_transcript.md` with your action log and
observable work transcript/summary.
"""


def expert_pancake_vertical_short() -> TaskDefinition:
    return TaskDefinition(
        task_id="expert_pancake_vertical_short",
        title="Expert Pancake Tutorial Extraction",
        source_worker="worker_5",
        generator_kind="direct_source",
        source_url="https://www.youtube.com/watch?v=45V4r4duCLU",
        clip_start_sec=0.0,
        clip_end_sec=294.0,
        prompt=PANCAKE_PROMPT,
        edit_decision_schema=_base_schema(
            ["source_ranges", "captions", "crop_decisions"],
            {
                "source_ranges": {"type": "array", "items": _range_schema, "minItems": 3},
                "captions": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
                "crop_decisions": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
                "audio_adjustments": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
            },
        ),
        ground_truth={
            "task_id": "expert_pancake_vertical_short",
            "source_url": "https://www.youtube.com/watch?v=45V4r4duCLU",
            "clip_start_sec": 0.0,
            "clip_end_sec": 294.0,
            "required_steps": [
                {"id": "pan_butter", "label": "grease pan with butter", "interval": [170.0, 190.0], "keywords": ["butter", "pan"]},
                {"id": "batter_pour", "label": "pour or swirl batter", "interval": [190.0, 212.0], "keywords": ["batter", "pour", "swirl"]},
                {"id": "bubble_cue", "label": "wait for bubbles", "interval": [212.0, 232.0], "keywords": ["bubble", "bubbles"]},
                {"id": "flip", "label": "flip with spatula", "interval": [232.0, 248.0], "keywords": ["flip", "spatula"]},
                {"id": "plate_finish", "label": "plate and finish", "interval": [248.0, 278.0], "keywords": ["plate", "finish", "syrup"]},
            ],
            "negative_intervals": [
                {"id": "amateur_montage", "interval": [0.0, 160.0]},
                {"id": "end_card_or_post_tutorial", "interval": [278.0, 294.0]},
            ],
        },
        verifier_config={
            "duration_gate": [50.0, 70.0],
            "duration_target": [55.0, 65.0],
            "aspect": "portrait_9_16",
            "min_height": 720,
            "weights": {
                "hard_1_format_duration": 0.10,
                "hard_2_source_authenticity_timeline": 0.16,
                "hard_3_expert_step_coverage_order": 0.27,
                "hard_4_negative_material_suppression": 0.15,
                "hard_5_vertical_roi_caption": 0.12,
                "hard_6_audio_quality_cut_smoothness": 0.10,
                "metadata": 0.10,
            },
        },
    )


def piecewise_av_sync_repair() -> TaskDefinition:
    return TaskDefinition(
        task_id="piecewise_av_sync_repair",
        title="Piecewise A/V Sync and Damage Repair",
        source_worker="worker_7",
        generator_kind="piecewise_av_corruption",
        source_url="https://www.youtube.com/watch?v=_aC3QUQp4FM",
        clip_start_sec=4.0,
        clip_end_sec=100.0,
        prompt=PIECEWISE_SYNC_PROMPT,
        edit_decision_schema=_base_schema(
            ["segments", "local_audio_shifts_ms", "removed_damage_ranges"],
            {
                "segments": {"type": "array", "items": _range_schema, "minItems": 2},
                "local_audio_shifts_ms": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["source_start", "source_end", "shift_ms"],
                        "properties": {
                            "source_start": {"type": "number", "minimum": 0},
                            "source_end": {"type": "number", "minimum": 0},
                            "shift_ms": {"type": "number"},
                            "reason": {"type": "string"},
                        },
                        "additionalProperties": True,
                    },
                },
                "removed_damage_ranges": {"type": "array", "items": _range_schema},
                "audio_filters": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
            },
        ),
        ground_truth={
            "task_id": "piecewise_av_sync_repair",
            "source_url": "https://www.youtube.com/watch?v=_aC3QUQp4FM",
            "clip_start_sec": 4.0,
            "clip_end_sec": 100.0,
            "corruption_recipe": {
                "black_leader_sec": 1.20,
                "black_tail_sec": 0.80,
                "freeze_splice": {"clean_time_sec": 47.5, "duration_sec": 0.75},
                "piecewise_audio_offsets": [
                    {"clean_start_sec": 0.0, "clean_end_sec": 31.5, "audio_delay_ms": 460},
                    {"clean_start_sec": 31.5, "clean_end_sec": 63.0, "audio_delay_ms": -320},
                    {"clean_start_sec": 63.0, "clean_end_sec": 96.0, "audio_delay_ms": 180},
                ],
            },
            "required_spans": [
                {"id": "opening_clap_demo", "interval": [0.0, 31.5], "weight": 0.35},
                {"id": "middle_explanation", "interval": [31.5, 63.0], "weight": 0.35},
                {"id": "final_explanation", "interval": [63.0, 96.0], "weight": 0.30},
            ],
        },
        verifier_config={
            "duration_gate": [88.0, 98.0],
            "duration_target": [90.0, 96.0],
            "aspect": "landscape_16_9",
            "resolution": [1280, 720],
            "weights": {
                "local_av_sync_repair": 0.45,
                "content_preservation_damage_cleanup": 0.35,
                "deliverable_quality_explainability": 0.20,
            },
        },
    )


def rough_interview_caption_cleanup() -> TaskDefinition:
    return TaskDefinition(
        task_id="rough_interview_caption_cleanup",
        title="Rough Interview Cleanup and Captioning",
        source_worker="worker_13",
        generator_kind="rough_interview",
        source_url="https://www.youtube.com/watch?v=Q-zuTZuYeCg",
        clip_start_sec=3279.0,
        clip_end_sec=3475.0,
        prompt=INTERVIEW_PROMPT,
        edit_decision_schema=_base_schema(
            ["kept_segments", "removed_defects", "caption_style"],
            {
                "kept_segments": {"type": "array", "items": _range_schema, "minItems": 2},
                "removed_defects": {"type": "array", "items": _range_schema},
                "caption_style": {"type": "object", "additionalProperties": True},
                "audio_filters": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
                "subtitle_generation": {"type": "object", "additionalProperties": True},
            },
        ),
        ground_truth={
            "task_id": "rough_interview_caption_cleanup",
            "source_url": "https://www.youtube.com/watch?v=Q-zuTZuYeCg",
            "clip_start_sec": 3279.0,
            "clip_end_sec": 3475.0,
            "defect_map": {
                "inserted_dead_air": [
                    {"clean_time_sec": 34.2, "duration_sec": 2.4},
                    {"clean_time_sec": 58.8, "duration_sec": 1.8},
                    {"clean_time_sec": 92.1, "duration_sec": 2.9},
                    {"clean_time_sec": 141.6, "duration_sec": 2.1},
                ],
                "repeated_phrase_loops": [
                    {"clean_start_sec": 49.0, "clean_end_sec": 52.2, "repeat_count": 2},
                    {"clean_start_sec": 118.4, "clean_end_sec": 121.0, "repeat_count": 2},
                ],
            },
            "semantic_anchors": [
                {"id": "young_people", "phrases": ["young people", "young"]},
                {"id": "motivation", "phrases": ["motivation", "motivated"]},
                {"id": "work", "phrases": ["work", "job", "career"]},
                {"id": "help", "phrases": ["help", "support", "thrive"]},
            ],
        },
        verifier_config={
            "duration_gate": [60.0, 75.0],
            "duration_target": [62.0, 72.0],
            "aspect": "landscape_16_9",
            "resolution": [1280, 720],
            "weights": {
                "speech_cleanup_semantic_preservation": 0.45,
                "caption_audio_deliverable_quality": 0.30,
                "source_fidelity_format_naturalness": 0.25,
            },
        },
    )


TASK_DEFINITIONS = {
    "expert_pancake_vertical_short": expert_pancake_vertical_short,
    "piecewise_av_sync_repair": piecewise_av_sync_repair,
    "rough_interview_caption_cleanup": rough_interview_caption_cleanup,
}
