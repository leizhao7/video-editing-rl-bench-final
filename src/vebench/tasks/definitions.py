from __future__ import annotations

from typing import Any

from .base import TaskDefinition


def _base_schema(required_extra: list[str], properties_extra: dict[str, Any]) -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "additionalProperties": True,
        "required": ["source_files", "tools_used", "checks_performed", *required_extra],
        "properties": {
            "source_files": {"type": "array", "items": {"type": "string"}, "minItems": 1},
            "tools_used": {"type": "array", "items": {"type": "string"}},
            "checks_performed": {
                "oneOf": [
                    {"type": "array", "items": {"type": "string"}},
                    {"type": "object", "additionalProperties": True},
                ]
            },
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


PANCAKE_CAPABILITY_TARGETS = {
    "primary": [
        "multimodal_grounding",
        "reasoning_over_a_plan",
    ],
    "secondary": [
        "tool_use_for_delivery",
        "self_correction_from_observations",
    ],
    "not_primary": [
        "a_v_sync_repair",
        "multi_source_editing",
        "object_removal_or_inpainting",
        "super_resolution_or_denoising",
        "frame_interpolation",
        "complex_motion_graphics",
        "reference_based_color_grading",
    ],
}


PANCAKE_LONG_HORIZON_STRUCTURE = {
    "genuinely_sequential_decisions": 6,
    "decision_count_range": [6, 6],
    "expected_tool_calls": {
        "typical": 12,
        "range": [9, 15],
        "counting_rule": (
            "Count media probes, frame/audio sampling calls, custom analysis scripts, render passes, "
            "and verification probes. A single ffmpeg command without prior observation/planning does "
            "not count as long-horizon."
        ),
    },
    "dependency_structure": [
        {
            "id": "probe_and_sample_source",
            "decision": "Confirm source metadata and create enough visual samples to understand the clip.",
            "depends_on": [],
            "typical_tools": ["ffprobe", "ffmpeg", "python"],
        },
        {
            "id": "select_expert_region",
            "decision": "Reject novice/blooper/reaction/end-card material and select the expert tutorial region.",
            "depends_on": ["probe_and_sample_source"],
            "typical_tools": ["frame_inspection", "optional_vlm"],
        },
        {
            "id": "map_recipe_steps",
            "decision": "Identify the ordered visual cooking actions that should appear in the tutorial.",
            "depends_on": ["select_expert_region"],
            "typical_tools": ["ffmpeg", "frame_inspection"],
        },
        {
            "id": "build_edit_plan",
            "decision": (
                "Choose source ranges, pacing, portrait crop strategy, and concise captions for a compact "
                "55-65 second edit."
            ),
            "depends_on": ["map_recipe_steps"],
            "typical_tools": ["python", "edit_decision_json", "frame_sampling"],
        },
        {
            "id": "render_vertical_short",
            "decision": "Render the vertical edit with selected trims, crop, captions, and audio normalization.",
            "depends_on": ["build_edit_plan"],
            "typical_tools": ["ffmpeg", "moviepy"],
        },
        {
            "id": "verify_and_patch",
            "decision": (
                "Probe and sample the rendered output, then patch the edit if duration, crop, step coverage, "
                "captions, or audio quality has a clear failure."
            ),
            "depends_on": ["render_vertical_short"],
            "typical_tools": ["ffprobe", "ffmpeg", "python", "opencv"],
        },
    ],
}


PANCAKE_REWARD_DESIGN = {
    "final_formula": {
        "hard_score": "0.20 * r_general + 0.80 * r_task",
        "with_llm_judge": "0.85 * r_hard + 0.15 * r_llm",
        "final_score": "min(final_before_caps, active_hard_caps)",
    },
    "r_general": {
        "description": "Delivery, media integrity, and provenance checks shared across tasks.",
        "components": {
            "r_format": {
                "weight": 0.30,
                "verifies": "Playable 9:16 output, duration gate, expected codec/resolution family.",
            },
            "r_audio_quality": {
                "weight": 0.20,
                "verifies": "Non-degenerate original audio with reasonable loudness and no clipping/silent padding.",
            },
            "r_video_quality": {
                "weight": 0.20,
                "verifies": "Non-degenerate video integrity without black/blank/frozen output artifacts.",
            },
            "r_source_authenticity": {
                "weight": 0.15,
                "verifies": "Output frames match the provided source and preserve a plausible source timeline.",
            },
            "r_provenance_and_logs": {
                "weight": 0.15,
                "verifies": "Valid edit_decision.json, source-range consistency, run history, and transcript.",
            },
        },
    },
    "r_task": {
        "description": "Task-specific checks focused on selecting the expert tutorial segment and organizing it as a compact recipe short.",
        "components": {
            "r_tutorial_segment_purity": {
                "weight": 0.25,
                "verifies": "Uses the expert tutorial region and suppresses novice attempts, bloopers, reactions, and end-card material.",
            },
            "r_temporal_order": {
                "weight": 0.20,
                "verifies": "Preserves source-time monotonicity and the cooking-step order.",
            },
            "r_visual_step_completeness": {
                "weight": 0.20,
                "verifies": "Covers the required visual cooking actions: pan prep, batter, bubbles, flip, and plated finish.",
            },
            "r_caption_visual_alignment": {
                "weight": 0.15,
                "verifies": "Captions are visible near the matching visual action, using metadata when present and visual fallback otherwise.",
            },
            "r_step_caption_completeness": {
                "weight": 0.10,
                "verifies": "Burned-in captions describe a coherent step-by-step method.",
            },
            "r_true_vertical_reframe": {
                "weight": 0.10,
                "verifies": "A real portrait crop/reframe keeps the cooking subject visible without black or blurred padding.",
            },
        },
    },
    "r_llm": {
        "weight_if_available": 0.15,
        "model_default": "gpt-5.5",
        "rubric_weights": {
            "step_caption_completeness": 0.30,
            "caption_visual_alignment": 0.25,
            "mobile_caption_readability": 0.20,
            "tutorial_naturalness": 0.15,
            "prompt_fit": 0.10,
        },
        "role": "Semantic judge for caption/action consistency, phone readability, tutorial naturalness, and prompt fit.",
    },
}


PANCAKE_REWARD_HACKING_MITIGATIONS = [
    {
        "hack": "Submit any portrait video or synthetic/generated footage.",
        "defense": [
            "source_match_fraction",
            "r_source_authenticity",
            "external_or_unmatched_material hard cap",
        ],
    },
    {
        "hack": "Use the wrong part of the source, such as novice failures, reactions, jokes, or end cards.",
        "defense": [
            "allowed_tutorial_intervals",
            "negative_intervals",
            "r_tutorial_segment_purity",
            "heavy_negative_material hard cap",
        ],
    },
    {
        "hack": "Delete most content to avoid negative material while losing the recipe.",
        "defense": [
            "r_visual_step_completeness",
            "pancake_visual_step_min",
            "weak_visual_step_completeness hard cap",
            "duration gate",
        ],
    },
    {
        "hack": "Reorder clips into a visually plausible but non-causal montage.",
        "defense": [
            "source_time_monotonicity",
            "r_temporal_order",
            "severe_order_failure hard cap",
        ],
    },
    {
        "hack": "Fake vertical format by centering landscape video over black bars or blurred padding.",
        "defense": [
            "top_bottom_black_padding_ratio",
            "top_bottom_blur_padding_ratio",
            "landscape_blur_padding_ratio",
            "fake_or_weak_vertical hard cap",
        ],
    },
    {
        "hack": "Add captions that exist in metadata but are invisible, huge, misplaced, or unrelated to the action.",
        "defense": [
            "caption_visual_presence",
            "r_caption_technical_quality",
            "r_caption_visual_alignment",
            "missing_or_invisible_captions hard cap",
            "LLM caption/action rubric when enabled",
        ],
    },
    {
        "hack": "Claim good edits in JSON without actually rendering them.",
        "defense": [
            "edit_media_consistency",
            "frame matching against output",
            "r_provenance_and_logs only partial credit",
            "LLM judge instructed not to reward unsupported claims",
        ],
    },
    {
        "hack": "Pad duration with silence, black frames, frozen frames, or unrelated filler.",
        "defense": [
            "duration target/gate",
            "audio_quality",
            "video_integrity",
            "tutorial_impurity_ratio",
            "negative/external material caps",
        ],
    },
]


PANCAKE_PROMPT = """# Task: Expert Pancake Tutorial Extraction

You are given `materials/source.mp4`, a landscape "50 People Try" pancake challenge video.

Create a 55-65 second vertical social tutorial that feels like a standalone pancake recipe short.

Find the expert/proficient pancake-making portion of the source and turn it into a clear
step-by-step tutorial. Do not build the edit around the novice blooper montage, failed attempts,
jokes, end cards, or unrelated banter.
Prefer a compact, coherent edit over a complex montage; use only as many cuts as needed to make the
tutorial clear.

Requirements:
- Export `submit/output.mp4` as portrait 9:16 H.264/AAC, preferably 1080x1920 or 720x1280.
- Use a true portrait crop/reframe. Do not fake vertical format by placing a landscape video inside
  black bars, blurred padding, or a decorative background.
- Keep pan, pancake, hands, spatula, and plated result visible in the vertical frame.
- Add short burned-in captions that break the method into clear sequential steps.
- Keep useful original cooking/speech audio, normalize loudness, and avoid clipping or silent padding.
- Do not add external footage, unrelated music, synthetic narration, generated visuals, or unrelated
  filler just to hit duration.
- Write `submit/edit_decision.json` with source ranges, output ranges, crop decisions, caption
  text/timing, audio adjustments, and measured self-checks.
- Write `submit/run_history.md` and `submit/agent_transcript.md` with your action log and
  observable work transcript/summary.
"""


PIECEWISE_SYNC_PROMPT = """# Task: Repair a Damaged Tutorial Clip

You are given `materials/source.mp4`, a rough 16:9 export of a creator tutorial.

Create:
- `submit/output.mp4`
- `submit/edit_decision.json`
- `submit/run_history.md`
- `submit/agent_transcript.md`

Requirements:
1. Inspect the media and identify technical issues that would make the clip unsuitable for publishing.
2. Produce a clean 16:9 MP4 that preserves the useful tutorial content in original order.
3. Keep the clap demonstration and the explanation of why creators clap before takes if they are
   useful to the final edit.
4. Remove non-content artifacts, repeated or broken material, dead air, and unusable sections.
5. Repair any audio/video timing issues you find.
6. Normalize speech loudness without clipping, muting, or replacing the original audio.
7. Export a standard landscape MP4: H.264 video, AAC audio, 1280x720, square pixels, 24-30 fps,
   duration 88-98 seconds.
8. Do not add external footage, synthetic speech, unrelated music, large overlays, or face-covering text.
9. Write `submit/edit_decision.json` with the issues you found, segment cuts, timing repairs,
   removed ranges, filters used, and measured final validation checks.
10. Write `submit/run_history.md` and `submit/agent_transcript.md` with your action log and
   observable work transcript/summary.
"""


PIECEWISE_SYNC_LONG_HORIZON_STRUCTURE = {
    "genuinely_sequential_decisions": 15,
    "expected_tool_calls": {
        "typical": 30,
        "range": [28, 34],
        "counting_rule": (
            "Count source probes, frame/audio sampling calls, custom analysis scripts, render calls, "
            "and final validation calls. One large ffmpeg command without observation-dependent "
            "diagnosis and planning is not a long-horizon solution."
        ),
    },
    "dependency_structure": [
        {"id": "read_constraints", "depends_on": [], "typical_tools": ["Read"]},
        {"id": "probe_source_metadata", "depends_on": ["read_constraints"], "typical_tools": ["ffprobe"]},
        {"id": "sample_global_frames", "depends_on": ["probe_source_metadata"], "typical_tools": ["ffmpeg", "opencv"]},
        {"id": "detect_boundary_padding", "depends_on": ["sample_global_frames"], "typical_tools": ["python", "opencv"]},
        {"id": "detect_visual_artifacts", "depends_on": ["sample_global_frames"], "typical_tools": ["python", "opencv"]},
        {"id": "extract_audio", "depends_on": ["probe_source_metadata"], "typical_tools": ["ffmpeg"]},
        {"id": "analyze_audio_quality", "depends_on": ["extract_audio"], "typical_tools": ["python", "librosa", "scipy"]},
        {"id": "find_multimodal_sync_anchors", "depends_on": ["sample_global_frames", "extract_audio"], "typical_tools": ["python", "opencv", "librosa"]},
        {"id": "choose_local_sync_zones", "depends_on": ["find_multimodal_sync_anchors"], "typical_tools": ["python"]},
        {"id": "estimate_local_audio_shifts", "depends_on": ["choose_local_sync_zones"], "typical_tools": ["python", "scipy"]},
        {"id": "choose_damage_removal_ranges", "depends_on": ["detect_boundary_padding", "detect_visual_artifacts"], "typical_tools": ["python"]},
        {"id": "choose_preserved_content_timeline", "depends_on": ["choose_damage_removal_ranges", "estimate_local_audio_shifts"], "typical_tools": ["python"]},
        {"id": "choose_audio_cleanup_strategy", "depends_on": ["analyze_audio_quality"], "typical_tools": ["ffmpeg", "librosa"]},
        {"id": "render_repaired_output", "depends_on": ["choose_preserved_content_timeline", "choose_audio_cleanup_strategy"], "typical_tools": ["ffmpeg", "python"]},
        {"id": "final_validation_and_documentation", "depends_on": ["render_repaired_output"], "typical_tools": ["ffprobe", "ffmpeg", "python"]},
    ],
}


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

Keep the edit plan compact. Use the transcript and visible source timecodes to choose a small set of
kept ranges, usually 4-7, that form one coherent answer. After the first export, check the rendered
file for duration, format, speech level, long pauses, caption visibility, and caption timing. If one
clear issue remains, repair it and export once more.

In `submit/edit_decision.json`, list kept source segments, removed defects or pauses, transcript
evidence for the kept idea, audio filters, subtitle generation method, caption style, final checks,
and any change made after checking the first export.

Also write `submit/run_history.md` and `submit/agent_transcript.md` with your action log and
observable work transcript/summary.
"""


INTERVIEW_LONG_HORIZON_STRUCTURE = {
    "genuinely_sequential_decisions": 10,
    "expected_tool_calls": {
        "typical": 20,
        "range": [18, 22],
        "counting_rule": (
            "Count source probes, transcript generation, frame/audio sampling, planning scripts, render calls, "
            "caption generation, and final validation. A single ffmpeg command without observation-dependent "
            "selection and checking does not satisfy the intended structure."
        ),
    },
    "dependency_structure": [
        {"id": "read_constraints", "depends_on": [], "typical_tools": ["Read"]},
        {"id": "probe_source", "depends_on": ["read_constraints"], "typical_tools": ["ffprobe"]},
        {"id": "sample_visual_audio", "depends_on": ["probe_source"], "typical_tools": ["ffmpeg", "opencv", "python"]},
        {"id": "transcribe_source", "depends_on": ["probe_source"], "typical_tools": ["faster-whisper"]},
        {"id": "map_core_answer", "depends_on": ["transcribe_source"], "typical_tools": ["python", "text review"]},
        {"id": "locate_cleanup_ranges", "depends_on": ["transcribe_source", "sample_visual_audio"], "typical_tools": ["python", "librosa"]},
        {"id": "choose_compact_timeline", "depends_on": ["map_core_answer", "locate_cleanup_ranges"], "typical_tools": ["python"]},
        {"id": "render_and_normalize", "depends_on": ["choose_compact_timeline"], "typical_tools": ["ffmpeg", "moviepy"]},
        {"id": "caption_output", "depends_on": ["render_and_normalize"], "typical_tools": ["faster-whisper", "ffmpeg"]},
        {"id": "validate_patch_package", "depends_on": ["caption_output"], "typical_tools": ["ffprobe", "python", "opencv"]},
    ],
}


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
                "source_ranges": {"type": "array", "items": _range_schema, "minItems": 1},
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
            "allowed_tutorial_intervals": [
                {"id": "expert_tutorial", "interval": [160.0, 278.0]},
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
            "general_weight": 0.20,
            "task_weight": 0.80,
            "llm_weight": 0.15,
            "capability_targets": PANCAKE_CAPABILITY_TARGETS,
            "long_horizon_structure": PANCAKE_LONG_HORIZON_STRUCTURE,
            "reward_design": PANCAKE_REWARD_DESIGN,
            "reward_hacking_mitigations": PANCAKE_REWARD_HACKING_MITIGATIONS,
            "general_weights": {
                "r_format": 0.30,
                "r_audio_quality": 0.20,
                "r_video_quality": 0.20,
                "r_source_authenticity": 0.15,
                "r_provenance_and_logs": 0.15,
            },
            "task_weights": {
                "r_tutorial_segment_purity": 0.25,
                "r_temporal_order": 0.20,
                "r_visual_step_completeness": 0.20,
                "r_caption_visual_alignment": 0.15,
                "r_step_caption_completeness": 0.10,
                "r_true_vertical_reframe": 0.10,
            },
            "hard_caps": {
                "missing_output_or_ffprobe": 0.0,
                "missing_audio_or_video": 0.25,
                "duration_outside_gate": 0.50,
                "wrong_aspect_or_resolution_family": 0.35,
                "fake_or_weak_vertical": 0.35,
                "weak_vertical_reframe": 0.60,
                "heavy_negative_material": 0.40,
                "external_or_unmatched_material": 0.35,
                "weak_visual_step_completeness": 0.55,
                "severe_order_failure": 0.60,
                "missing_or_invisible_captions": 0.70,
                "weak_step_captions": 0.65,
            },
        },
    )


def piecewise_av_sync_repair() -> TaskDefinition:
    return TaskDefinition(
        task_id="piecewise_av_sync_repair",
        title="Repair a Damaged Tutorial Clip",
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
                "flash_insert": {"clean_time_sec": 23.8, "duration_sec": 0.70, "color": "white"},
                "duplicate_insert": {"clean_start_sec": 72.0, "clean_end_sec": 74.2, "repeat_count": 1},
                "audio_gain_segments": [
                    {"clean_start_sec": 48.0, "clean_end_sec": 72.0, "gain_db": -7.0}
                ],
                "piecewise_audio_offsets": [
                    {"clean_start_sec": 0.0, "clean_end_sec": 24.0, "audio_delay_ms": 720},
                    {"clean_start_sec": 24.0, "clean_end_sec": 48.0, "audio_delay_ms": -650},
                    {"clean_start_sec": 48.0, "clean_end_sec": 72.0, "audio_delay_ms": 480},
                    {"clean_start_sec": 72.0, "clean_end_sec": 96.0, "audio_delay_ms": -380},
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
            "general_weight": 0.20,
            "task_weight": 0.80,
            "hard_task_weight": 0.85,
            "llm_weight": 0.15,
            "content_full_credit_fraction": 0.90,
            "expected_sync_anchors": 12,
            "general_weights": {
                "r_format": 0.40,
                "r_audio_quality": 0.25,
                "r_artifact_completeness": 0.20,
                "r_provenance_and_logs": 0.15,
            },
            "task_weights": {
                "r_av_sync_segmented": 0.22,
                "r_av_sync_global": 0.18,
                "r_visual_artifact_cleanup": 0.18,
                "r_content_preservation": 0.16,
                "r_duplicate_or_bad_insert_cleanup": 0.12,
                "r_audio_cleanup": 0.08,
                "r_black_boundary_cleanup": 0.06,
            },
            "capability_mix": {
                "targets": [
                    "reasoning_over_a_plan",
                    "tool_use",
                    "multimodal_grounding",
                ],
                "does_not_target": [
                    "self_correction_from_intermediate_observations",
                    "vlm_endpoint_use",
                    "nle_scripting",
                    "generative_video_or_audio",
                ],
            },
            "long_horizon_structure": PIECEWISE_SYNC_LONG_HORIZON_STRUCTURE,
            "sync_segments": [
                {"id": "opening", "interval": [0.0, 24.0], "weight": 0.25},
                {"id": "middle_pre_splice", "interval": [24.0, 47.5], "weight": 0.25},
                {"id": "middle_post_splice", "interval": [47.5, 72.0], "weight": 0.25},
                {"id": "late", "interval": [72.0, 96.0], "weight": 0.25},
            ],
            "hard_caps": {
                "missing_output_or_ffprobe": 0.0,
                "missing_audio_or_video": 0.25,
                "duration_outside_gate": 0.50,
                "task_below_0_30": 0.45,
                "content_preservation_below_0_70": 0.60,
                "required_span_coverage_below_0_85": 0.60,
                "any_required_span_below_0_75": 0.70,
                "source_time_monotonicity_below_0_80": 0.65,
                "black_boundary_cleanup_below_0_50": 0.70,
                "visual_artifact_cleanup_below_0_50": 0.70,
                "duplicate_cleanup_below_0_50": 0.70,
                "audio_cleanup_below_0_40": 0.75,
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
            ["kept_segments", "removed_defects", "caption_style", "source_evidence", "final_checks"],
            {
                "kept_segments": {"type": "array", "items": _range_schema, "minItems": 2},
                "removed_defects": {"type": "array", "items": _range_schema},
                "caption_style": {"type": "object", "additionalProperties": True},
                "source_evidence": {"type": "array", "items": {"type": "object", "additionalProperties": True}, "minItems": 2},
                "final_checks": {"type": "object", "additionalProperties": True},
                "revision_notes": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
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
                {"id": "leader_hiring_gen_z", "phrases": ["hiring gen z", "hiring gen zee", "gen z"]},
                {"id": "thrive_motivation_goals", "phrases": ["thrive stay motivated", "stay motivated", "achieve their goals", "thrive"]},
                {"id": "strengths_weaknesses_frame", "phrases": ["strengths and weaknesses", "biggest weakness", "perfectionist"]},
                {"id": "strengths_have_liabilities", "phrases": ["strengths often have liability", "strengths often have", "liability"]},
                {"id": "confidence_arrogance_context", "phrases": ["confident", "arrogant", "wrong context"]},
                {"id": "weaknesses_silver_linings", "phrases": ["weaknesses also have", "silver linings", "server linings"]},
                {"id": "chronically_disorganized", "phrases": ["chronically disorganized", "disorganized"]},
                {"id": "systems_do_not_stick", "phrases": ["system", "worked for like a week", "back to being disorganized"]},
                {"id": "context_it_depends", "phrases": ["it depends", "answer is it depends", "context"]},
                {"id": "characteristics_strength_or_weakness", "phrases": ["characteristics", "huge strengths", "huge weaknesses"]},
                {"id": "careful_labeling_generations", "phrases": ["label people or generations", "strong or weak", "stronger weak"]},
                {"id": "gen_z_activist", "phrases": ["very activist", "activist"]},
                {"id": "hated_jobs_silence", "phrases": ["hated their jobs", "suffered in silence"]},
            ],
        },
        verifier_config={
            "duration_gate": [60.0, 75.0],
            "duration_target": [62.0, 72.0],
            "aspect": "landscape_16_9",
            "resolution": [1280, 720],
            "long_horizon_structure": INTERVIEW_LONG_HORIZON_STRUCTURE,
            "final_weights": {
                "r_general": 0.20,
                "r_task": 0.80,
            },
            "task_mix_weights": {
                "r_hard_task": 0.85,
                "r_llm": 0.15,
            },
            "general_weights": {
                "format_compliance": 0.28,
                "source_match_fraction": 0.18,
                "video_integrity": 0.14,
                "audio_quality": 0.14,
                "edit_decision_schema": 0.09,
                "run_history_transcript_score": 0.04,
                "r_grounded_evidence_and_checks": 0.05,
                "r_anti_reward_hacking": 0.08,
            },
            "hard_task_weights": {
                "speech_cleanup_hard": 0.28,
                "semantic_anchor_preservation": 0.24,
                "caption_hard_quality": 0.24,
                "audio_normalization": 0.13,
                "r_grounded_evidence_and_checks": 0.04,
                "r_anti_reward_hacking": 0.07,
            },
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
