# Proposed Three-Task Benchmark

These tasks are designed for a CPU-first video server. They avoid requiring local GPU models while
still exercising multi-step editing, verification, and reward-hacking analysis.

## Task 1: `silence_filler_trim`

Prompt:

> Create a polished version of the source clip by removing long pauses and filler-word segments
> while preserving all substantive speech and keeping audio/video synchronized. Return
> `output.mp4` and `edit_decision.json`.

Source materials:

```text
materials/source.mp4
materials/transcript.json       # word-level or phrase-level timestamps
materials/style_notes.md
```

Generator:

Create or collect a talking-head style clip, then inject known silence/filler intervals. Store hidden
ground truth intervals in `ground_truth.json`.

Verifier dimensions:

1. Removal accuracy: output should remove at least 80% of annotated pause/filler time.
2. Speech preservation: output should preserve at least 95% of non-target speech duration.
3. A/V integrity: duration, audio energy, and frame continuity should not show padding, black
   screens, or desync.

Hackability:

An agent could delete too much to remove all target intervals. Bound this with speech preservation
and transcript coverage checks. It could pad with silence to hit duration; detect low-RMS spans and
compare output duration against expected edited duration.

Horizon:

Expected 8-15 tool calls: inspect metadata, extract audio, inspect transcript, plan cut list, render
first pass, probe output, measure silences, revise cuts, export final.

## Task 2: `av_sync_repair`

Prompt:

> The source video has audio/video sync errors. Detect and repair the offset or drift. Preserve the
> visual content, audio content, resolution, and duration as much as possible. Return `output.mp4`
> and `edit_decision.json`.

Source materials:

```text
materials/desynced.mp4
materials/notes.md
```

Generator:

Create clips with visible clap/flash events paired with audio beeps, then apply a hidden constant
offset or mild drift to the audio stream.

Verifier dimensions:

1. Sync error: cross-correlate visual flash intensity with beep onset; reward low residual offset.
2. Content preservation: compare frame/audio fingerprints against the source after correcting the
   known transform.
3. Format compliance: output must be playable, same nominal resolution/fps, and no duplicated
   black lead-in.

Hackability:

An agent could mute audio or replace it with synthetic beeps. Bound this by checking audio
fingerprint similarity and non-beep background preservation. It could crop out flashes; bound with
frame similarity and resolution checks.

Horizon:

Expected 6-12 tool calls: probe streams, extract audio/events, sample frames, estimate offset,
apply shift/filter, verify residual error, iterate.

## Task 3: `vertical_reframe`

Prompt:

> Convert the source landscape clip into a 9:16 social video. Keep the primary speaker/object
> visible and centered through shot changes, preserve the original audio, and add readable subtitles
> from the provided transcript. Return `output.mp4` and `edit_decision.json`.

Source materials:

```text
materials/source_landscape.mp4
materials/transcript.srt
materials/target_description.md
```

Generator:

Use synthetic or lightly controlled footage with a colored target/speaker moving across a landscape
frame. Hidden ground truth stores the target center over time. This keeps verification deterministic
without a local detector.

Verifier dimensions:

1. Reframe geometry: output is 9:16, expected resolution, and duration-preserving.
2. Target containment: sample frames and verify the target color/blob remains inside safe margins.
3. Subtitle timing/legibility: parse subtitle sidecar or run a visual subtitle-band check; use VLM or
   human review only as a tiebreaker for typography.

Hackability:

An agent could zoom out with pillarboxing to keep everything visible. Penalize black bars and
require the target to occupy a reasonable area. It could ignore subtitles; detect subtitle-band
activity at transcript intervals and require sidecar text match.

Horizon:

Expected 10-18 tool calls: probe, scene detect, sample frames, infer target motion/crops, generate
crop schedule, style subtitles, render, sample output, adjust margins, final export.

