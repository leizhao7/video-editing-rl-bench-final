# Selected Task: Expert Pancake Tutorial Extraction

Source proposal: based on `worker_5`, improved for verifier robustness and long-horizon RL use.

## 1. Metadata

- Task ID: `expert_pancake_vertical_short`
- Source worker: `worker_5`
- Real-world editing scenario: A social-media editor receives a noisy challenge-style cooking video and must extract the useful expert demonstration into a concise, standalone vertical recipe tutorial.
- Difficulty: medium-hard
- Expected semantic steps: 12
- Expected runtime per agent: 35-75 minutes
- Main capabilities tested: source inspection, transcript-guided source selection, positive/negative interval discrimination, step-order preservation, vertical reframing, captions, audio cleanup, render validation, self-check and revision.

## 2. Why This Task Was Selected

This is the strongest worker 1-5 proposal because it has a clean RL training signal. The agent must
do more than trim and transcode: it has to find the expert material hidden inside a noisy source,
reject visually tempting novice/blooper material, preserve an ordered recipe sequence, reframe
cooking actions for mobile, add useful captions, normalize audio, and verify the output.

The key advantage is verifier design. The task can use hidden positive intervals for expert recipe
steps and hidden negative intervals for amateur montage/end-card content. That makes reward
hacking harder than in tasks where any source-derived clip can pass.

## 3. YouTube Source Videos

Primary source:

| Role | URL | Channel/title | Clip start | Clip end | Why it fits | Main risk |
| --- | --- | --- | --- | --- | --- | --- |
| Primary | https://www.youtube.com/watch?v=45V4r4duCLU | Epicurious, `50 People Try to Make Pancakes` | 00:00 | 04:54 | Contains noisy amateur attempts followed by a clearer expert/proficient pancake sequence. This creates both positive and negative verifier intervals. | Fast cuts and music can make source matching noisy; expert intervals must be manually locked during packaging. |

Backups:

| Role | URL | Channel/title | Clip start | Clip end | Why it fits | Main risk |
| --- | --- | --- | --- | --- | --- | --- |
| Backup 1 | https://www.youtube.com/watch?v=KdD2Vm3pzeo | Epicurious, `50 People Try to Dice An Onion` | 00:00 | 03:20 | Same noisy-to-expert format with clear hand/action steps. | Knife/hand ROI moves more, so crop verification is harder. |
| Backup 2 | https://www.youtube.com/watch?v=xR0_ips5I_o | Epicurious, `50 People Try to Make a Grilled Cheese Sandwich` | 00:00 | 06:29 | Similar expert extraction problem with pan, flip, and final food result. | More steam/music/sizzle interference; longer packaging effort. |

Primary provenance:

```json
{
  "source": "youtube",
  "url": "https://www.youtube.com/watch?v=45V4r4duCLU",
  "video_id": "45V4r4duCLU",
  "title": "50 People Try to Make Pancakes | Epicurious",
  "channel": "Epicurious",
  "clip_start_sec": 0.0,
  "clip_end_sec": 294.0,
  "estimated_duration_sec": 294.0,
  "downloaded_filename": "source.mp4"
}
```

## 4. Agent-Facing Prompt

```text
You are given materials/source.mp4, a landscape "50 People Try" pancake challenge video.

Create a 55-65 second vertical social tutorial that feels like a standalone pancake recipe short.

Use the expert/proficient pancake-making sequence. Do not build the edit around the novice
blooper montage, failed attempts, jokes, end cards, or unrelated banter.

The final story must show these recipe steps in order:
1. grease the pan with butter,
2. pour or swirl the batter,
3. wait for bubbles as the doneness cue,
4. flip with a spatula,
5. plate and finish the pancake.

Requirements:
- Export submit/output.mp4 as portrait 9:16 H.264/AAC, preferably 1080x1920 or 720x1280.
- Keep pan, pancake, hands, spatula, and plated result visible in the vertical frame.
- Add short burned-in captions for each recipe step.
- Keep useful original cooking/speech audio, normalize loudness, and avoid clipping or silent padding.
- Do not add external footage, unrelated music, synthetic narration, or generated visuals.
- Write submit/edit_decision.json with source ranges, output ranges, crop decisions, caption text/timing, audio adjustments, and measured self-checks.
```

## 5. Long-Horizon Step Plan

| Step | Required decision/action | Tools/libraries | Observable artifact |
| ---: | --- | --- | --- |
| 1 | Probe streams, duration, fps, resolution, codecs, and audio properties. | `ffprobe`, `ffmpeg` | Metadata notes. |
| 2 | Build contact sheets or preview frames to understand amateur, expert, and end-card sections. | `ffmpeg`, `Pillow`, `cv2` | Source contact sheet. |
| 3 | Extract audio and run ASR to locate recipe-step language and separate expert instruction from chatter. | `ffmpeg`, `faster-whisper`, `librosa` | Timestamped transcript and silence map. |
| 4 | Identify candidate positive expert intervals for the five required recipe steps. | transcript + frame review | Candidate step intervals. |
| 5 | Identify negative intervals: novice failures, jokes, repeated banter, sponsor/end-card sections. | transcript + frame review | Rejected interval list. |
| 6 | Choose a concise 55-65s sequence covering all five steps in order, with enough visual evidence per step. | planning JSON/table | Draft edit plan. |
| 7 | Refine cut points to avoid mid-word cuts, long dead air, and confusing scene jumps. | waveform/ASR review, `librosa` | Clean cut list. |
| 8 | Design 9:16 crop/keyframes for each segment so action ROIs stay visible. | `cv2`, frame sampling, `ffmpeg` crop | Crop plan/keyframes. |
| 9 | Create concise step captions and align them to edited output timing. | SRT/ASS, `ffmpeg subtitles` | Caption sidecar/filter graph. |
| 10 | Normalize audio and add short fades where cuts would pop. | `ffmpeg loudnorm`, `pydub`, `librosa` | Audio filter settings. |
| 11 | Render final MP4 and validate format, duration, streams, audio, black/freeze, captions, and crop. | `ffmpeg`, `ffprobe`, Python validators | `submit/output.mp4`, self-check. |
| 12 | Revise if validation fails and write truthful `edit_decision.json`. | JSON schema, rerender tools | Final deliverables. |

## 6. Public Materials

```text
materials/
  source.mp4
  prompt.md
  tools.md
  edit_decision.schema.json
  output_specs.json
```

Public sidecars:

- `prompt.md`: the agent-facing prompt above.
- `tools.md`: CPU-first tool list and common inspection/render commands.
- `edit_decision.schema.json`: required shape for source ranges, output ranges, crops, captions, audio ops, and self-checks.
- `output_specs.json`: duration bounds, accepted resolutions, codec/container requirements, caption safe-area rules.

No public transcript and no public positive/negative timestamps. The agent must inspect the media.

## 7. Private Materials

```text
private/
  ground_truth.json
  verifier_config.json
  source_asr_words.json
  source_frame_index.npz
  source_audio_index.npz
  roi_keyframes.json
```

Private generation:

- `ground_truth.json`: locked source provenance, target duration/specs, positive expert intervals, negative intervals, required step labels, keyword anchors, and score caps.
- `source_asr_words.json`: `faster-whisper` word-level transcript, manually spot-checked around positive/negative intervals.
- `source_frame_index.npz`: source frames sampled every 0.5s with pHash, HSV histograms, low-res SSIM thumbnails, and precomputed candidate portrait crops.
- `source_audio_index.npz`: MFCC/log-mel fingerprints for source-derived audio checks.
- `roi_keyframes.json`: manually annotated ROIs for pan, batter, bubbles, spatula/flip, and plated result at key source timestamps.

Initial positive intervals, to be verified after packaging:

```json
{
  "pan_butter": [170.0, 190.0],
  "batter_pour": [190.0, 212.0],
  "bubble_cue": [212.0, 232.0],
  "flip": [232.0, 248.0],
  "plate_finish": [248.0, 278.0]
}
```

Initial negative intervals, to be verified after packaging:

```json
{
  "amateur_montage": [0.0, 160.0],
  "end_card_or_post_tutorial": [278.0, 294.0]
}
```

## 8. Hard Verifier

Hard verifier computes from `submit/output.mp4` first. `edit_decision.json` is used for metadata
quality and consistency checks only; it cannot rescue a bad render.

### Mandatory Gates

| Gate | Method | Failure behavior |
| --- | --- | --- |
| Output exists | Check path and nonzero file size. | total = 0.0 |
| ffprobe readable | Parse `ffprobe` JSON. | total = 0.0 |
| Streams present | Require decodable video and audio streams. | total = 0.0 |
| Duration plausible | Gate: 50-70s; target reward: 55-65s. | outside gate total = 0.0 |
| Portrait 9:16 | Require display aspect within 2%, minimum 720px height, no large pillarbox. | total = 0.0 if wrong aspect |
| Non-black/non-frozen | Sample 2 fps; luma/variance/pHash diversity thresholds. | total = 0.0 if degenerate |
| Audio usable | RMS, clipping, silence ratio, and speech-like energy checks. | total = 0.0 if silent/clipped |
| Edit log schema | Validate JSON schema and legal times. | metadata = 0; total capped at 0.85 if missing/invalid |

### Dense Hard Rewards

Weights sum to 1.0.

| Reward ID | Weight | Measures | Calculation | Full credit | Anti-hack guard |
| --- | ---: | --- | --- | --- | --- |
| `hard_1_format_duration` | 0.10 | Export compliance and target duration. | ffprobe metadata; duration curve full in 55-65s, linear to 0 at 50/70s; codec/resolution/SAR checks. | Portrait H.264/AAC, 55-65s, sane fps/bitrate. | Prevents odd containers, padding, or raw unedited duration. |
| `hard_2_source_authenticity_timeline` | 0.16 | Output derives from source and uses multiple real intervals. | Map output frames/audio to source with pHash/HSV/SSIM/MFCC; smooth with monotonic timeline matching. | >=85% non-caption/non-title seconds source-matched, >=4 distinct source spans, no single span >35s. | Catches unrelated clips, still loops, whole-source copy, and fake JSON. |
| `hard_3_expert_step_coverage_order` | 0.27 | Five required expert recipe steps appear in order. | Use source-time mapping plus positive intervals; per step: visual seconds up to 0.8 + keyword/caption support up to 0.2; apply order multiplier. | All five steps have >=2.5 matched seconds, keyword support, and monotonic first appearances. | Prevents one-step highlights, generic pancake montage, or captions over wrong visuals. |
| `hard_4_negative_material_suppression` | 0.15 | Novice montage, jokes, and end-card material are excluded. | Sum output seconds mapped to negative intervals; subtract forbidden transcript phrases. | <=4s negative leakage and no strong forbidden phrase hits. | If negative leakage >18s, cap total score at 0.55 even if other metrics pass. |
| `hard_5_vertical_roi_containment` | 0.12 | Action remains visible in the portrait crop. | For mapped positive frames, compare output against ROI keyframes/candidate crops; score ROI visible area and edge distance. | >=85% positive-step samples keep action ROI inside central safe area. | Penalizes pillarboxing, center crops that lose the pan, and captions covering action. |
| `hard_6_caption_presence_alignment` | 0.10 | Step captions are visibly present and speech/step aligned. | Validate declared captions, then sample frames for high-contrast text-like overlays in safe region during step intervals. | Captions for at least 5 steps, visible, not huge, not covering ROI. | Random text or JSON-only captions get partial credit only; LLM judges semantics. |
| `hard_7_audio_quality_cut_smoothness` | 0.10 | Audio is clear, normalized, and not padded. | RMS/loudness proxy, peak/clipping, silence gaps, short-window discontinuities near detected cuts. | -24 to -14 dBFS proxy, clipping <0.1%, silence <12%, no severe pops. | Catches muting, over-limiting, silent padding, and rough cut hiding. |

## 9. LLM Judge

LLM judge weight in total score: 20%. It receives only a compact evidence pack.

Evidence pack:

- Source contact sheet: novice section, expert intervals, final/end-card section.
- Output contact sheet: evenly sampled frames plus one frame per detected step caption.
- Source transcript snippets: positive expert intervals and negative interval examples.
- Output ASR transcript.
- `edit_decision.json` summary.
- Hard verifier summary with failure flags.
- Optional five short 3s before/after clips around required steps.

LLM rubric:

| LLM Reward | Weight | Question |
| --- | ---: | --- |
| `llm_tutorial_completeness` | 0.45 | Does the output clearly teach the five-step pancake process as a standalone short? |
| `llm_continuity_pacing` | 0.25 | Does it flow naturally without confusing jumps, repeated shots, or rushed audio? |
| `llm_mobile_readability` | 0.20 | Are framing and captions usable on a phone? |
| `llm_prompt_fit` | 0.10 | Does it feel like an expert tutorial rather than a comedy blooper montage? |

Expected structured output:

```json
{
  "tutorial_completeness": 0.0,
  "continuity_pacing": 0.0,
  "mobile_readability": 0.0,
  "prompt_fit": 0.0,
  "major_failures": [],
  "rationale": ""
}
```

## 10. Final Score

```text
if mandatory_degenerate_gate_fails:
    total = 0.0
else:
    hard_score = weighted_sum(hard_1..hard_7)
    llm_score = weighted_sum(llm_tutorial_completeness,
                             llm_continuity_pacing,
                             llm_mobile_readability,
                             llm_prompt_fit)
    metadata_score = (
        0.35 * schema_completeness +
        0.25 * timestamp_consistency_against_detected_source_matches +
        0.20 * crop_caption_audio_detail +
        0.20 * measured_self_check_quality
    )
    total = 0.70 * hard_score + 0.20 * llm_score + 0.10 * metadata_score
```

Caps:

- If `hard_4_negative_material_suppression < 0.30`, cap total at 0.55.
- If `hard_3_expert_step_coverage_order < 0.40`, cap total at 0.60.
- If source authenticity is below 0.50, cap total at 0.40.
- If `edit_decision.json` contradicts detected media for more than half the output, cap metadata at 0.30.

## 11. Reward-Hacking Analysis

| Hack | Why it is tempting | Verifier response |
| --- | --- | --- |
| Submit black/still portrait video. | Easy duration/aspect. | Non-black/non-frozen gate and source-authenticity reward fail. |
| Copy the whole source into portrait. | Avoids source selection. | Duration gate, negative leakage, and timeline diversity penalize. |
| Use funny novice clips because they are visually active. | They fill time and look entertaining. | Negative interval suppression and prompt-fit LLM score penalize; high leakage caps total. |
| Show only flip/final pancake. | Attractive and easy. | Step coverage/order requires all five steps. |
| Add correct captions over wrong visuals. | Text can spoof keyword checks. | Step score needs visual positive-interval matches; caption semantics mostly LLM. |
| Use unrelated pancake footage. | Could look better. | Source frame/audio matching collapses. |
| Mute audio or add music. | Hides rough cuts. | Audio gate, ASR/caption support, and source audio matching penalize. |
| Pad with title cards, silence, or frozen frames. | Hits duration. | Source-authentic seconds, silence, and freeze checks penalize. |
| Fake `edit_decision.json`. | Metadata is easy to write. | Metadata is only 10% and cross-checked against detected source mapping. |
| Pillarbox landscape source. | Simplest 9:16 conversion. | Aspect gate, border stats, ROI containment, and LLM readability penalize. |

## 12. Implementation Notes

Verifier can be implemented with the existing CPU stack:

- `ffprobe` for streams, duration, resolution, codecs.
- `ffmpeg` for extraction, downsampling, audio decode, frame sampling.
- `faster-whisper` for source/output ASR.
- `opencv-python`, `Pillow`, `scikit-image`, `numpy` for frame matching, pHash/SSIM proxies, border checks, caption-band heuristics, ROI containment.
- `librosa`, `soundfile`, `pydub`, `scipy` for RMS, silence, clipping, audio fingerprints, cut discontinuities.
- `jsonschema`, `pydantic`, `pandas` for schema validation and score reporting.

Implementation risk is medium-high because vertical output-to-source matching under crops and
captions is noisy. Mitigation: sample sparsely, mask caption bands, precompute several legal 9:16
source crop templates per timestamp, combine visual and audio matching, and score seconds/intervals
rather than exact frames.

## 13. Why This Is Good for Long-Horizon RL

This task has a natural dependency chain: inspect source -> discover useful expert segment -> reject
negative material -> preserve ordered recipe steps -> design crop/captions/audio -> render -> verify
and revise. Failures are informative: an agent can pass format while failing source discovery, pass
step coverage while failing crop, or pass crop while leaking novice footage. That creates dense,
diagnostic rewards suitable for RL rather than a brittle pass/fail benchmark.

