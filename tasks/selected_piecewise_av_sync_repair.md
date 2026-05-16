# Selected Task: Piecewise A/V Sync and Damage Repair

Source proposal: based on `worker_7`, improved against the Philo take-home requirements.

## 1. Metadata

- Task ID: `piecewise_av_sync_repair`
- Source worker: `worker_7`
- Task type: technical repair / synchronization
- Real-world editing scenario: A creator recorded a short tutorial with separate camera and audio, but the ingest/export pipeline introduced multiple local A/V offsets, black leader/tail, a freeze/dead-air splice, mild hum, and uneven speech gain. The agent must repair the damaged clip into a publication-ready excerpt.
- Difficulty: medium-hard
- Expected semantic steps: 12
- Expected tool calls: roughly 20-35, depending on how much the agent iterates.
- Final benchmark role: complementary to content-selection/social-edit tasks such as `expert_pancake_vertical_short`.

## 2. Why This Improves Worker 7

Worker 7 had the right core idea: a repair task with private clean-reference scoring. This improved
version tightens it for the PDF requirements:

- Defines exactly 3 top-level scoring dimensions with clear level definitions.
- Keeps dense submetrics under those dimensions for RL signal density.
- Makes the automation boundary explicit: deterministic hard verifier, LLM judge, human review.
- Adds a task generator spec so the package is self-contained and reproducible.
- Adds dependency structure, not only a list of steps.
- Removes the ambiguous idea that an output close to the clean reference should be penalized. If the
  public package leaks the clean URL, that is an environment/data-leakage failure, not a verifier
  scoring rule. The scorer should reward a clean-reference-quality repair.

## 3. Task Generator

The task is generated from a clean YouTube clip, but the editing agent only receives the corrupted
public source. The clean reference, original URL, and corruption recipe are private.

Primary source candidate:

```json
{
  "source": "youtube",
  "url": "https://www.youtube.com/watch?v=_aC3QUQp4FM",
  "video_id": "_aC3QUQp4FM",
  "title": "The Clap (Syncing sound on your videos)",
  "channel": "Red Book Productions",
  "clip_start_sec": 4.0,
  "clip_end_sec": 100.0,
  "clean_duration_sec": 96.0,
  "private_filename": "clean_reference.mp4",
  "public_filename": "source.mp4"
}
```

Generator output:

```text
tasks/piecewise_av_sync_repair/
  public/
    materials/source.mp4
    prompt.md
    tools.md
    edit_decision.schema.json
  private/
    clean_reference.mp4
    corruption_recipe.json
    required_spans.json
    anchor_windows.json
    clean_reference_features.npz
    reference_transcript.json
    verifier_config.json
```

Deterministic corruption recipe, example:

```json
{
  "seed": 7017,
  "baseline": {
    "resolution": "1280x720",
    "fps": 30,
    "audio_sample_rate": 48000,
    "video_codec": "h264",
    "audio_codec": "aac"
  },
  "black_leader_sec": 1.20,
  "black_tail_sec": 0.80,
  "freeze_splice": {
    "clean_time_sec": 47.5,
    "duration_sec": 0.75,
    "audio_action": "insert_low_level_room_tone"
  },
  "piecewise_audio_offsets": [
    {"clean_start_sec": 0.0, "clean_end_sec": 31.5, "audio_delay_ms": 460},
    {"clean_start_sec": 31.5, "clean_end_sec": 63.0, "audio_delay_ms": -320},
    {"clean_start_sec": 63.0, "clean_end_sec": 96.0, "audio_delay_ms": 180}
  ],
  "audio_defects": {
    "hum_hz": 60,
    "hum_gain_db": -28,
    "zone_gain_db": [0.0, -4.0, 2.5],
    "noise_floor_db": -42
  }
}
```

Important packaging rule:

```text
Do not expose the clean YouTube URL, clean_reference.mp4, or corruption_recipe.json to the
editing agent. Prefer running agent containers without network access for this task.
```

## 4. Agent-Facing Prompt

```text
You are given materials/source.mp4, a damaged 16:9 tutorial excerpt from a creator.

The clip has multiple technical defects:
- audio/video sync is wrong by different amounts in different parts of the clip;
- there is black leader and black tail;
- there is one accidental freeze/dead-air splice;
- speech loudness is uneven and there may be mild hum/noise.

Create:
- submit/output.mp4
- submit/edit_decision.json

Requirements:
1. Repair A/V sync locally. Do not assume a single global audio offset is enough.
2. Remove black leader/tail and the accidental freeze/dead-air splice.
3. Preserve the useful tutorial content in original order, including the clap demonstration and the explanation of why creators clap before takes.
4. Keep natural pacing. Do not delete explanation just to make sync easier.
5. Normalize speech loudness without clipping, muting, or replacing the original audio.
6. Export a standard landscape MP4: H.264 video, AAC audio, 1280x720, square pixels, 24-30 fps, duration 88-98 seconds.
7. Do not add external footage, synthetic speech, unrelated music, large overlays, or face-covering text.
8. Write submit/edit_decision.json with segment cuts, estimated local audio shifts, removed damage ranges, filters used, and measured self-checks.
```

## 5. Horizon and Dependency Structure

Expected semantic steps:

| Step | Decision | Depends on | Tools |
| ---: | --- | --- | --- |
| 1 | Probe stream metadata and output constraints. | none | `ffprobe` |
| 2 | Extract preview frames and audio waveform. | step 1 | `ffmpeg`, `librosa`, `Pillow` |
| 3 | Detect black leader/tail and frozen/dead-air splice candidates. | step 2 | `cv2`, `numpy`, `librosa` |
| 4 | Locate sync anchor regions: clap transient, visible hand impact, speech/mouth/gesture windows. | step 2 | `cv2`, `scipy`, `librosa` |
| 5 | Decide segmentation boundaries where offsets likely change. | steps 3-4 | Python planning |
| 6 | Estimate first local offset. | step 4 | onset detection, frame-difference analysis |
| 7 | Estimate middle local offset after damage boundary. | steps 4-5 | local correlation |
| 8 | Estimate final local offset and confirm one global shift is insufficient. | steps 4-5 | local correlation |
| 9 | Build repaired timeline: remove defects, apply piecewise shifts, preserve content order. | steps 3, 5-8 | `ffmpeg`, `moviepy` or `av` |
| 10 | Normalize audio and reduce hum/noise conservatively. | step 9 | `ffmpeg`, `pydub`, `noisereduce` |
| 11 | Render draft and self-check duration, black/freeze, silence, loudness, and local sync. | steps 9-10 | `ffprobe`, `cv2`, `librosa` |
| 12 | Revise and write final output plus truthful edit decision log. | step 11 | `ffmpeg`, `jsonschema` |

Dependency graph:

```text
probe
  -> frame/audio extraction
      -> damage detection -> timeline cuts
      -> sync-anchor detection -> local offset estimates
          -> piecewise repair render
              -> audio cleanup
                  -> self-check
                      -> revision/final output
```

This is long-horizon because bad early diagnoses poison later edits. For example, if the agent
mistakes the freeze splice for a sync offset boundary, later local shifts will align one anchor while
breaking another.

## 6. Capability Mix

Targets:

- Reasoning over a plan: infer that there are several local defects, not one global issue.
- Tool use: `ffprobe`, `ffmpeg`, custom Python analysis, audio correlation, frame sampling.
- Multimodal grounding: align audio transients with visual clap/gesture frames and match speech windows to video windows.
- Self-correction: render drafts, inspect residual sync, adjust offsets/cuts, re-render.
- Artifact production: deliver a playable, publication-ready MP4 and structured edit log.

Does not target:

- Object removal, inpainting, segmentation, super-resolution, frame interpolation, lip-sync generation, motion graphics, or cinematic color grading.
- Subjective highlight selection. The content to preserve is defined by private required spans.
- Open-world semantic understanding beyond the LLM judge's continuity/polish tiebreaker.

Difficulty gradient:

```text
Harder than a simple trim/caption/reframe task because the main decision is diagnostic:
where did the timeline break, and how much local offset should be applied in each region?

Easier than true lip-sync generation or inpainting because all source audio/video content already
exists and the repair can be done with deterministic timing edits.
```

## 7. Public and Private Materials

Public materials:

```text
materials/source.mp4
materials/prompt.md
materials/tools.md
materials/edit_decision.schema.json
```

Private materials:

```text
private/clean_reference.mp4
private/corruption_recipe.json
private/required_spans.json
private/anchor_windows.json
private/clean_reference_features.npz
private/reference_transcript.json
private/verifier_config.json
```

Ground-truth criteria checked by the scorer:

- residual A/V sync error against private clean reference;
- required content span coverage and source-time order;
- black/freeze/silence damage removal;
- speech loudness, clipping, hum/noise, and pacing;
- output format and rate integrity;
- edit decision log consistency.

## 8. Scoring Dimensions

The PDF asks for 1-3 scoring dimensions per task. This task uses 3 top-level dimensions, each with
dense submetrics for RL signal.

### Dimension A: Local A/V Sync Repair

Weight: 0.45

Classification: hard-to-hack, because residuals are measured against private clean-reference
audio/video features that the agent cannot see.

Level definitions:

| Score | Definition |
| ---: | --- |
| 1.0 | Median residual <= 40 ms and p90 residual <= 80 ms across anchor windows; all offset zones aligned. |
| 0.7 | Most anchors are improved, but one zone remains mildly off, typically 80-160 ms. |
| 0.4 | A single global shift improves one anchor but leaves another zone visibly wrong. |
| 0.0 | Sync is unchanged, worse, or cannot be measured because audio/video was replaced, muted, or degenerated. |

Dense submetrics:

- `sync_median_residual_ms`
- `sync_p90_residual_ms`
- `anchor_match_coverage`
- `piecewise_improvement_over_damaged`
- `rate_integrity`

Calculation:

1. Sample anchor windows from `anchor_windows.json`.
2. For each output window, match video frames to clean-reference time using pHash/SSIM/ORB.
3. Match audio to clean-reference time using onset/MFCC cross-correlation.
4. Residual is `audio_matched_time - video_matched_time`.
5. Score median and p90 absolute residuals, with unmatched windows receiving zero subscore.

### Dimension B: Content Preservation and Damage Cleanup

Weight: 0.35

Classification: hackable but bounded. A policy can trim aggressively to avoid hard repair windows,
but required-span coverage, order checks, and duration gates cap that strategy.

Level definitions:

| Score | Definition |
| ---: | --- |
| 1.0 | Required tutorial spans are preserved in order, black leader/tail and freeze/dead-air are removed, and no major explanatory content is lost. |
| 0.7 | Most required spans are present, with minor over-trimming or one remaining small damage artifact. |
| 0.4 | Output is watchable but drops a required explanation, keeps obvious damage, or has awkward order/gaps. |
| 0.0 | Output is mostly black/frozen/silent, deletes most content, or uses unrelated material. |

Dense submetrics:

- `required_span_coverage`
- `source_time_monotonicity`
- `black_frame_ratio`
- `freeze_run_max_sec`
- `silence_run_max_sec`
- `audio_quality`

Calculation:

Use clean-reference matching to map output windows to source time. Compute coverage of
`required_spans.json`, source-time monotonicity, and damage cleanup from final video/audio.

### Dimension C: Deliverable Quality and Explainability

Weight: 0.20

Classification: mixed. Format and metadata consistency are hackable but bounded; perceived polish
is soft/vibes and only useful as a tiebreaker.

Level definitions:

| Score | Definition |
| ---: | --- |
| 1.0 | Output is standard 1280x720 H.264/AAC, clear audio, no visual artifacts, and edit log accurately describes repairs and self-checks. |
| 0.7 | Technically playable with minor format/audio/log omissions. |
| 0.4 | Playable but rough: weak loudness, incomplete repair log, or visible/pacing artifacts. |
| 0.0 | Wrong format, missing edit log, incoherent output, or obvious presentation failure. |

Dense submetrics:

- `format_compliance`
- `audio_loudness_clipping`
- `edit_decision_schema`
- `edit_decision_consistency`
- `llm_watchability`
- `llm_continuity`

Calculation:

Hard verifier handles format/audio/log consistency. LLM judge receives compact evidence and scores
only perceived sync/watchability, continuity, and polish.

## 9. Mandatory Gates

| Gate | Method | Failure behavior |
| --- | --- | --- |
| Output exists | Path and file size check. | total = 0.0 |
| ffprobe readable | Parse streams and format JSON. | total = 0.0 |
| Required streams | At least one decodable video stream and one decodable audio stream. | total = 0.0 |
| Duration | 88-98 seconds. | outside range total = 0.0; near-boundary subscore falls off. |
| Resolution/aspect | 1280x720 or exact 16:9 equivalent, square pixels. | wrong aspect total = 0.0 |
| Non-degenerate video | Not mostly black, not mostly frozen. | total = 0.0 if degenerate |
| Non-degenerate audio | Not silent, not heavily clipped. | total = 0.0 if degenerate |
| Edit log parseable | `submit/edit_decision.json` valid JSON and schema-compatible. | metadata subscore = 0; total capped at 0.85 |

## 10. Reward Vector

Verifier output should be a dense JSON vector:

```json
{
  "task_id": "piecewise_av_sync_repair",
  "total": 0.0,
  "suspected_reward_hacking": false,
  "gates": {
    "output_exists": true,
    "ffprobe_readable": true,
    "has_audio_video": true,
    "duration_valid": true,
    "format_valid": true,
    "non_degenerate_video": true,
    "non_degenerate_audio": true,
    "edit_decision_valid": true
  },
  "dimensions": {
    "local_av_sync_repair": 0.0,
    "content_preservation_damage_cleanup": 0.0,
    "deliverable_quality_explainability": 0.0
  },
  "hard_subscores": {
    "sync_median_residual_ms": 0.0,
    "sync_p90_residual_ms": 0.0,
    "anchor_match_coverage": 0.0,
    "required_span_coverage": 0.0,
    "source_time_monotonicity": 0.0,
    "damage_cleanup": 0.0,
    "audio_quality": 0.0,
    "rate_integrity": 0.0,
    "format_compliance": 0.0,
    "edit_decision_consistency": 0.0
  },
  "llm_scores": {
    "perceived_sync_watchability": 0.0,
    "tutorial_continuity": 0.0,
    "edit_polish": 0.0
  },
  "diagnostics": []
}
```

Final formula:

```text
if any fatal gate fails:
    total = 0.0
else:
    total =
      0.45 * local_av_sync_repair
    + 0.35 * content_preservation_damage_cleanup
    + 0.20 * deliverable_quality_explainability
```

Caps:

```text
if source_authenticity < 0.50:
    total <= 0.25
if local_av_sync_repair < 0.35:
    total <= 0.55
if required_span_coverage < 0.45:
    total <= 0.60
if output contains > 4s continuous black/freeze/silence padding:
    total <= 0.50
if edit_decision contradicts detected timeline for > 50% of output:
    deliverable_quality_explainability <= 0.45
```

## 11. Automation Boundary

| Check | Deterministic hard verifier | LLM judge | Human review |
| --- | --- | --- | --- |
| ffprobe readability, streams, duration, resolution | yes | no | no |
| black leader/tail removal | yes | no | no |
| frozen/dead-air splice removal | yes | no | optional only for debugging |
| local A/V residual against clean reference | yes | no | optional spot check |
| content preservation/order | mostly yes | yes for continuity tiebreaker | optional |
| audio loudness/clipping/noise | yes | no | no |
| perceived sync naturalness | partial | yes | optional |
| edit polish/publishability | partial | yes | optional |

LLM judge input should be compact:

- damaged-source contact sheet;
- output contact sheet;
- 3 short before/after excerpts around anchor windows;
- output transcript excerpt;
- hard verifier summary;
- edit decision summary.

LLM structured output:

```json
{
  "perceived_sync_watchability": 0.0,
  "tutorial_continuity": 0.0,
  "edit_polish": 0.0,
  "major_failures": [],
  "rationale": ""
}
```

LLM score should not exceed 20% of total and should never override failed hard gates.

## 12. Hackability Analysis

| Scoring dimension | Cheat strategy | Classification | Detection / bound |
| --- | --- | --- | --- |
| Local A/V Sync Repair | Apply one global shift. | Hackable but bounded | Local residual checked across multiple offset zones; one zone may improve but others fail. |
| Local A/V Sync Repair | Replace audio with silence or music. | Hard-to-hack | Audio presence, source audio matching, ASR continuity, and sync anchor coverage fail. |
| Local A/V Sync Repair | Time-stretch video/audio until one anchor aligns. | Hackable but bounded | Rate-integrity checks source-time slope and duplicated/dropped frame ratio. |
| Content Preservation | Keep only easy-to-sync clap moments. | Hackable but bounded | Required span coverage, duration, transcript continuity, and LLM continuity cap score. |
| Content Preservation | Pad with black, still frames, or silence. | Hackable but bounded | Black/freeze/silence detectors and source-authenticity checks cap total. |
| Content Preservation | Reorder snippets. | Hard-to-hack | Clean-reference source-time monotonicity catches order violations. |
| Deliverable Quality | Fake `edit_decision.json`. | Hackable but bounded | Metadata is small weight and is cross-checked against detected timeline. |
| Deliverable Quality | Hide mouth/clap with overlays. | Hackable but bounded | Overlay/visual-integrity checks plus LLM evidence pack penalize. |
| Deliverable Quality | Make output close to clean reference via leaked URL. | Environment leakage, not reward hack | Prevent by not exposing URL/reference and running no-network. A perfect repair should score high if produced from available materials. |

## 13. Implementation Feasibility

CPU tools are sufficient:

- `ffmpeg` and `ffprobe`: probing, trimming, concat, audio shifting, filters, extraction.
- `numpy`, `scipy`: cross-correlation, onset timing, signal math.
- `librosa`, `soundfile`, `pydub`: audio decode, RMS, MFCC/log-mel, silence/noise checks.
- `opencv-python`, `Pillow`, `scikit-image`: frame sampling, pHash/SSIM/ORB-like matching, black/freeze detection.
- `faster-whisper`: optional transcripts for continuity evidence.
- `jsonschema`, `pydantic`, `pandas`: validation and score reporting.

Prototype baseline agents:

| Baseline | Expected score behavior |
| --- | --- |
| `copy_input` | Fails black/freeze/sync cleanup; low total. |
| `trim_only` | Removes leader/tail but leaves local offsets; medium-low. |
| `global_shift` | Improves one zone but fails piecewise residual; medium. |
| `oracle_recipe` | Uses private corruption recipe; high score. |
| `mute_audio` | Fails audio/source/sync; near-zero despite clean video. |

These baselines are useful for verifier calibration before running Codex/Claude/Gemini.

## 14. Why This Is Good for Long-Horizon RL

This task is a strong RL environment because it has hidden state the agent must infer from media,
not from prompt text. The correct repair requires a chain of dependent decisions: identify damage,
find sync anchors, infer offset zones, apply piecewise edits, preserve content, normalize audio,
render, measure residuals, and revise. The reward is dense enough to guide learning but still
anchored in private ground truth, making shallow hacks less attractive.

It also improves the overall benchmark portfolio. Paired with `expert_pancake_vertical_short`,
it covers a different axis:

```text
pancake task: semantic source selection + social repurposing
sync task: technical diagnosis + local media repair
```

That gives the final three-task benchmark a real capability mix instead of three versions of
"turn a tutorial into a vertical short."

