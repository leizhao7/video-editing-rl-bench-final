# Worker Prompt: YouTube Video Editing RL Task Design

You are one of 10 worker agents helping design a mini benchmark for long-horizon agentic video
editing RL. Your job is to find suitable YouTube source videos and design exactly one benchmark
task proposal. You are not implementing the verifier code yet. You are designing the task, source
selection, scoring rubric, hard verifier, LLM judge, and reward-hacking defenses.

Write your final output as exactly one Markdown file in:

```text
tasks/worker_<id>_<task_slug>.md
```

Use the format in:

```text
tasks/TASK_PROPOSAL_TEMPLATE.md
```

## Benchmark Goal

The benchmark should evaluate coding/video-editing agents in a long-horizon RL setting. A good
task should require the agent to inspect media, plan edits, run multiple tools, render an output,
self-check the result, and revise. It should not be solvable by one trivial ffmpeg command.

Design for:

- 8-15 semantic steps per task; 10-14 is the ideal band for this first benchmark.
- Count meaningful editing decisions, not command count. Do not count `ffmpeg` invocations as
  separate steps unless they reflect a distinct editing decision.
- 1-3 source videos per task, with one primary YouTube source and backups.
- 4-6 hard verifier dimensions.
- 2-4 LLM judge dimensions.
- Dense reward vectors, not only pass/fail.
- Strong reward-hacking analysis.

The final benchmark will later be packaged as self-contained tasks with public materials,
private ground truth, verifier/scorer code, and a `tasks_and_rubrics.tsv` summary.

## Available CPU-First Environment

Assume the editing agent and verifier can use these tools. Do not design a task that requires a
local GPU model.

Shell commands:

- `ffmpeg`: trim, concat, transcode, crop, pad, audio shift, filters, subtitles, frame extraction.
- `ffprobe`: metadata, duration, fps, resolution, codecs, streams.
- `python >= 3.11`
- `bash`

Python packages:

- `numpy`
- `scipy`
- `opencv-python` / `cv2`
- `moviepy`
- `av`
- `librosa`
- `soundfile`
- `pydub`
- `scenedetect`
- `faster-whisper`
- `Pillow`
- `scikit-image`
- `pandas`
- `pydantic`
- `tqdm`
- `colour-science`
- `noisereduce`
- `imageio`
- `imageio-ffmpeg`
- `matplotlib`
- `jsonschema`

Useful capabilities this environment can support:

- Metadata probing and media validation.
- Trimming, cutting, concatenation, transcoding.
- Audio extraction, silence detection, RMS/loudness analysis.
- Audio shift and simple sync repair.
- Scene cut detection.
- Frame sampling, contact sheets, image statistics.
- Basic object/region tracking using OpenCV heuristics when the target is visually clear.
- Simple subtitle generation/burn-in if transcripts or timestamps are available.
- Simple color/exposure/contrast checks.
- Basic denoise/loudness normalization.
- Verifier reports in JSON/TSV.

Before proposing the task, first reason about the tool boundary:

- What can these packages objectively measure or transform?
- Which parts of the proposed task can be verified with deterministic code?
- Which parts would require an LLM judge?
- Which parts are outside the environment and should be removed or simplified?

Avoid requiring these unless the task can be judged through API calls or simplified proxies:

- True object removal / video inpainting.
- High-quality super-resolution.
- Frame interpolation.
- Lip-sync generation.
- Robust open-world segmentation.
- Reference-based cinematic grading.
- Complex motion graphics.

## Realistic Task Discovery

Do not treat the list below as a required menu. These are examples of realistic editing jobs, not
categories you must force your task into. Your priority is to design a task that a real creator,
editor, social-media operator, podcast producer, educator, or marketing team might actually ask for.

You may choose one example, combine ideas, or propose a different realistic task. The task is valid
only if it can be executed and verified with the CPU-first environment above.

Example real-world task patterns:

- Clean up a podcast/interview clip by removing long pauses, filler words, repeated phrases, or dead air.
- Repair A/V sync in a clip where speech, claps, impacts, or visible gestures reveal the offset.
- Reformat a landscape clip into a 9:16 social video while preserving the main subject.
- Make a 30-60s scene-aware highlight montage from a longer vlog, tutorial, demo, travel, sports, or event clip.
- Align, repair, or burn in subtitles for a short social or educational clip.
- Clean noisy speech audio, normalize loudness, and remove dead air without damaging content.
- Combine 2-3 related clips into a coherent short edit with a beginning, middle, and end.
- Extract action moments from sports, fitness, cooking, crafting, gaming, or performance footage.
- Turn a longer tutorial/product explanation into a concise instructional short.
- Fix format compliance problems such as aspect ratio, black bars, loudness, title card, and export specs.

If you propose a novel task, explicitly explain why it is a real editing need and why it is feasible
with these tools.

## YouTube Source Selection Rules

Find at least 3 candidate YouTube videos and choose one primary source. For each candidate include:

- URL.
- Title/channel if available.
- Exact proposed clip start and end timestamps.
- Why it fits the task.
- Risks, such as jump cuts, music, subtitles, scene complexity, low resolution, or weak verifier signal.

Even though this is for private/internal testing, do not put downloaded videos in the repo. The
proposal should only store URLs, clip ranges, metadata, and design notes.

Good YouTube sources:

- Talking-head interviews, podcasts, lectures, tutorials, vlogs.
- Videos with visible claps, beeps, impacts, musical hits, or speech mouth movement for sync tasks.
- Landscape videos with a clearly visible moving subject for vertical reframe tasks.
- Travel, cooking, sports, fitness, product demos, and tutorials with clear shot boundaries for montage.

Bad sources:

- Highly edited shorts that already have no pauses.
- Music videos where copyright/audio analysis makes the task noisy.
- Clips with too many fast cuts if the verifier depends on tracking.
- Very low-resolution or heavily compressed videos.
- Videos where the target object/person is ambiguous for most of the clip.

## Verifier Design Principles

Split the verifier into two major classes:

1. Hard verifier: objective, programmatic checks.
2. LLM judge: semantic/aesthetic checks that are hard to measure with code.

Hard verifier should dominate the score. Recommended default:

```text
mandatory gates: required
hard verifier: 70%
LLM judge: 20%
metadata/edit_decision quality: 10%
```

For subjective montage tasks, you may use:

```text
hard verifier: 55%
LLM judge: 35%
metadata/edit_decision quality: 10%
```

Mandatory hard gates should include:

- `submit/output.mp4` exists.
- `ffprobe` can read the output.
- Required audio/video streams exist.
- Duration is inside the allowed range.
- Resolution and aspect ratio match the task.
- Output is not black, frozen, or trivially blank.
- Audio is not silent or clipped unless task explicitly allows silence.
- `submit/edit_decision.json` exists and follows a JSON schema.

Hard rewards should be computed from the final video whenever possible, not merely from the
agent's claimed edit decisions. Examples:

- Silence removed while preserving non-target speech.
- A/V sync residual offset after repair.
- Target bbox/region containment inside a safe crop area.
- Scene boundary cut quality.
- Output duration and format compliance.
- Audio loudness and clipping.
- Frame similarity or content preservation.
- Subtitle timing and visibility.

LLM judge should receive a compact evidence pack, not an entire unbounded video:

- Source contact sheet.
- Output contact sheet.
- Source/output transcript snippets with timestamps.
- edit decision summary.
- hard verifier summary.
- a few short before/after excerpts if necessary.

LLM judge should output structured JSON with 2-4 scores and short rationale. It should judge things
like semantic continuity, naturalness, whether important information was preserved, and whether the
edit satisfies the prompt intent.

## Reward Design Requirements

For every reward you propose, explain:

- The reward name.
- Whether it is hard or LLM-based.
- Its weight.
- The exact inputs used.
- The calculation method.
- Full-credit threshold.
- Partial-credit curve.
- How it prevents or detects reward hacking.

Use dense scores from 0.0 to 1.0 where possible. Avoid binary-only scoring except for mandatory
gates.

## Reward-Hacking Analysis

List at least 5 plausible cheating strategies. Examples:

- Outputting a black screen or unrelated stock clip.
- Muting audio to hide sync/noise problems.
- Deleting too much content to satisfy duration/silence targets.
- Speeding up the whole video instead of making intelligent cuts.
- Padding with silence or still frames.
- Faking `edit_decision.json`.
- Cropping/padding to satisfy aspect ratio while losing the subject.
- Overusing subtitles/text overlays to hide bad editing.

For each hack, explain the detector or penalty.

## Required Final Markdown Sections

Your Markdown proposal must include:

1. Metadata.
2. Environment fit check.
3. YouTube source videos.
4. Task prompt draft.
5. Long-horizon step plan.
6. Capabilities tested.
7. Public materials.
8. Hidden ground truth/private materials.
9. Hard verifier design.
10. LLM judge design.
11. Final score formula.
12. Reward hacking analysis.
13. Implementation feasibility.
14. Why this is good for long-horizon RL.

Be concrete. A strong proposal should be specific enough that another engineer can implement the
task package and verifier without asking you what the task meant.
