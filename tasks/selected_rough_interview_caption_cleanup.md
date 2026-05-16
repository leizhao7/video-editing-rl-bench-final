# Selected Task: Rough Interview Cleanup and Captioning

Source proposal: based on `worker_13`, improved against the Philo take-home requirements.

## 1. Metadata

- Task ID: `rough_interview_caption_cleanup`
- Source worker: `worker_13`
- Task type: speech-editing / captioning / interview polish
- Real-world editing scenario: A social-media editor receives a rough interview excerpt with inserted dead air, repeated phrase loops, and mild room noise. The editor must produce a clean, captioned 60-75 second educational clip while preserving the speaker's meaning.
- Difficulty: medium
- Expected semantic steps: 12
- Expected tool calls: roughly 20-35.
- Portfolio role: third axis after content-selection/social-editing and technical A/V repair.

## 2. Why This Task Was Selected

Worker 13 is the best worker 11-16 proposal because it avoids the two already selected capability
axes. It is not a recipe/tutorial vertical short and not another A/V sync repair. It tests a practical
speech-editing workflow:

- inspect a rough long interview excerpt;
- transcribe it;
- remove inserted dead air and repeated phrase loops;
- preserve semantic anchors;
- clean and normalize speech audio;
- generate and burn accurate captions;
- produce an auditable edit log.

This is a real creator/editor request and is verifier-friendly because the benchmark can inject known
defects into a public rough source while keeping a private clean reference and defect map.

## 3. Task Generator

The task generator starts from a clean YouTube interview segment, then creates a rough public source
with deterministic defects. The editing agent sees only the rough public source.

Primary source candidate:

```json
{
  "source": "youtube",
  "url": "https://www.youtube.com/watch?v=Q-zuTZuYeCg",
  "video_id": "Q-zuTZuYeCg",
  "title": "Simon Sinek: The Number One Reason Why You're Not Succeeding | E145",
  "channel": "The Diary Of A CEO",
  "clip_start_sec": 3279.0,
  "clip_end_sec": 3475.0,
  "clean_duration_sec": 196.0,
  "private_filename": "clean_reference.mp4",
  "public_filename": "source.mp4"
}
```

Generator output:

```text
tasks/rough_interview_caption_cleanup/
  public/
    materials/source.mp4
    prompt.md
    tools.md
    source_metadata.json
    edit_decision.schema.json
  private/
    clean_reference.mp4
    defect_map.json
    reference_transcript.json
    semantic_anchors.json
    reference_audio_stats.json
    source_fingerprints.npz
    verifier_config.json
```

Example deterministic defect recipe:

```json
{
  "seed": 13013,
  "inserted_dead_air": [
    {"clean_time_sec": 34.2, "duration_sec": 2.4},
    {"clean_time_sec": 58.8, "duration_sec": 1.8},
    {"clean_time_sec": 92.1, "duration_sec": 2.9},
    {"clean_time_sec": 141.6, "duration_sec": 2.1}
  ],
  "repeated_phrase_loops": [
    {"clean_start_sec": 49.0, "clean_end_sec": 52.2, "repeat_count": 2},
    {"clean_start_sec": 118.4, "clean_end_sec": 121.0, "repeat_count": 2}
  ],
  "audio_defects": {
    "broadband_noise_db": -38,
    "room_tone_gain_db": -32,
    "zone_gain_db": [0.0, -3.5, 2.0]
  },
  "video_defects": {
    "preserve_original_picture": true,
    "no_synthetic_black_frames": true
  }
}
```

Packaging rule:

```text
Do not expose the original YouTube URL, clean_reference.mp4, defect_map.json, or semantic anchors
to the editing agent during evaluation. Prefer no-network agent containers.
```

If the clean source leaks and an agent uses it, that is an environment leakage problem. The verifier
should reward a clean, correct, source-derived edit, but the benchmark runner should prevent direct
access to private references.

## 4. Agent-Facing Prompt

```text
You are editing a rough interview excerpt into a polished educational social clip.

Input:
- materials/source.mp4 is a rough 16:9 interview excerpt.

Create:
- submit/output.mp4
- submit/captions.srt
- submit/edit_decision.json

Output requirements:
- 60-75 seconds total duration.
- 1280x720, 16:9, H.264 video with AAC audio.
- Preserve a clear self-contained explanation about helping young people stay motivated and thrive at work.
- Remove long dead air, obvious false starts, and repeated phrase loops while keeping speech natural.
- Keep the main speaker's meaning intact. Do not reorder ideas in a way that changes the argument.
- Normalize spoken audio so it is comfortably listenable without clipping or pumping.
- Add readable burned-in captions for all spoken words, and save the timing as submit/captions.srt.
- Avoid black frames, frozen frames, unrelated footage, background music, synthetic narration, and heavy decorative overlays.

In submit/edit_decision.json, list kept source segments, removed defects or pauses, audio filters,
subtitle generation method, caption style, and measured self-checks.
```

## 5. Horizon and Dependency Structure

Expected semantic steps:

| Step | Decision | Depends on | Tools |
| ---: | --- | --- | --- |
| 1 | Probe streams, duration, fps, frame size, codecs, and audio layout. | none | `ffprobe` |
| 2 | Extract audio, waveform, contact sheet, and rough transcript. | step 1 | `ffmpeg`, `faster-whisper`, `librosa`, `Pillow` |
| 3 | Locate long pauses, rough dead air, and noise/gain problems. | step 2 | `librosa`, `pydub`, `numpy` |
| 4 | Locate repeated phrase loops and false starts from transcript timing. | step 2 | transcript analysis |
| 5 | Identify semantic spine: setup/question, main claim, supporting explanation, closing line. | steps 2-4 | LLM/agent reasoning over transcript |
| 6 | Choose 3-6 kept source segments totaling 60-75s. | steps 3-5 | edit planning |
| 7 | Cut and stitch segments at word/silence-safe boundaries. | step 6 | `ffmpeg`, `moviepy` |
| 8 | Normalize audio and lightly reduce noise without damaging speech. | step 7 | `ffmpeg`, `pydub`, `noisereduce` |
| 9 | Generate SRT captions aligned to edited output speech. | step 7 | `faster-whisper`, custom SRT writer |
| 10 | Burn captions with safe placement and readable line breaks. | step 9 | `ffmpeg subtitles/drawtext` |
| 11 | Self-check duration, stream specs, pauses, repeats, clipping, caption timing, and visual integrity. | steps 7-10 | `ffprobe`, `librosa`, `cv2` |
| 12 | Revise and write final output, SRT, and truthful edit decision log. | step 11 | render + `jsonschema` |

Dependency graph:

```text
probe -> extract audio/transcript/frames
      -> defect detection -> removal candidates
      -> semantic-spine selection -> keep segments
          -> rough cut -> audio cleanup -> captions -> burn-in
              -> self-check -> revision/final output
```

This is long-horizon because the edit is not a global `silenceremove` pass. Removing too much can
destroy meaning; preserving too much leaves injected roughness; captions must be retimed after the
final cut.

## 6. Capability Mix

Targets:

- Reasoning over a plan: choose a coherent educational arc, not just the loudest or shortest moments.
- Tool use: ffmpeg, ffprobe, custom Python audio/transcript analysis, subtitle writing.
- Multimodal grounding: align output speech, captions, and visible interview frames.
- Self-correction: render, transcribe/check output, revise cuts/captions/audio.
- Artifact production: video, sidecar captions, and auditable edit log.

Does not target:

- A/V sync diagnosis, object removal, segmentation, super-resolution, frame interpolation, lip-sync generation, or complex motion graphics.
- Dynamic action tracking. The visual task is intentionally simple; the hard part is speech editing and captions.

Difficulty gradient:

```text
Easier than piecewise A/V repair because there is no local sync diagnosis.
Harder than simple silence removal because the agent must preserve semantic anchors, remove repeated loops,
retime captions after edits, and avoid over-deleting speech.
```

## 7. Public and Private Materials

Public materials:

```text
materials/source.mp4
materials/prompt.md
materials/tools.md
materials/source_metadata.json
materials/edit_decision.schema.json
```

Expected submission:

```text
submit/output.mp4
submit/captions.srt
submit/edit_decision.json
```

Private materials:

```text
private/clean_reference.mp4
private/defect_map.json
private/reference_transcript.json
private/semantic_anchors.json
private/reference_audio_stats.json
private/source_fingerprints.npz
private/verifier_config.json
```

Ground-truth criteria checked by scorer:

- removal of injected dead-air pads;
- suppression of repeated phrase loops;
- preservation of semantic anchor phrases and order;
- natural speech pacing and audio quality;
- caption timing, coverage, and visible burn-in;
- source fidelity, format compliance, and edit-log consistency.

## 8. Scoring Dimensions

The PDF asks for 1-3 scoring dimensions per task. This task uses 3 dimensions with dense
subscores.

### Dimension A: Speech Cleanup and Semantic Preservation

Weight: 0.45

Classification: hackable but bounded. A policy can over-delete to remove all defects, but semantic
anchor recall, duration constraints, and transcript preservation cap that behavior.

Level definitions:

| Score | Definition |
| ---: | --- |
| 1.0 | Injected pauses and repeated loops are removed while the core argument remains ordered and self-contained. |
| 0.7 | Most roughness is removed, with one minor repeat/pause or one weak semantic transition. |
| 0.4 | Output is shorter and cleaner but loses important context or keeps several rough defects. |
| 0.0 | Output is unchanged, mostly deleted, semantically incoherent, or unrelated. |

Dense submetrics:

- `inserted_pause_removed_ratio`
- `max_internal_silence_sec`
- `repeat_loop_suppression`
- `semantic_anchor_recall`
- `anchor_order_score`
- `duplicate_ngram_rate`

Calculation:

Use `defect_map.json` and ASR transcripts to detect whether known dead-air pads and repeated phrase
loops survive in the output. Use `semantic_anchors.json` plus ordered transcript matching to score
meaning preservation.

### Dimension B: Caption and Audio Deliverable Quality

Weight: 0.30

Classification: mixed. Subtitle timing and audio statistics are deterministic; caption readability is
partly soft and should use LLM only as a tiebreaker.

Level definitions:

| Score | Definition |
| ---: | --- |
| 1.0 | Captions cover nearly all speech, are well timed and visible, and speech audio is clean and normalized. |
| 0.7 | Captions/audio are usable with small timing, line-break, or loudness issues. |
| 0.4 | Captions exist but are poorly timed/partial, or audio is rough but intelligible. |
| 0.0 | Captions are missing/invisible, audio is silent/clipped, or subtitle text does not match speech. |

Dense submetrics:

- `srt_token_coverage`
- `srt_median_timing_error_ms`
- `burned_caption_visibility`
- `caption_safe_area_score`
- `speech_loudness_score`
- `clipping_noise_score`

Calculation:

Parse `submit/captions.srt`, compare it to output ASR, sample frames during speech to detect
text-like overlays, and compute audio RMS/peak/noise/silence statistics.

### Dimension C: Source Fidelity, Format, and Naturalness

Weight: 0.25

Classification: mixed. Source/format checks are deterministic and bounded; edit naturalness is
soft/vibes and should not dominate reward.

Level definitions:

| Score | Definition |
| ---: | --- |
| 1.0 | Output is source-derived, correct format, visually valid, and feels like a natural interview clip. |
| 0.7 | Technically valid with minor cut or metadata issues. |
| 0.4 | Playable but choppy, poorly logged, or only weakly source-matched. |
| 0.0 | Wrong format, unrelated media, fake metadata, or obvious degenerate output. |

Dense submetrics:

- `format_compliance`
- `source_fidelity`
- `cut_boundary_quality`
- `nonblack_nonfrozen_video`
- `edit_decision_consistency`
- `llm_semantic_naturalness`

Calculation:

Use `ffprobe`, source fingerprints, frame/audio matching, cut-boundary audio energy, and
`edit_decision.json` consistency checks. LLM judge contributes only to naturalness/readability.

## 9. Mandatory Gates

| Gate | Method | Failure behavior |
| --- | --- | --- |
| Output exists | Check `submit/output.mp4`. | total = 0.0 |
| ffprobe readable | Parse streams and format JSON. | total = 0.0 |
| Required streams | At least one decodable video and audio stream. | total = 0.0 |
| Duration | 60-75 seconds. | outside range total = 0.0 |
| Resolution/aspect | 1280x720 or exact 16:9 equivalent. | wrong aspect total = 0.0 |
| Non-degenerate video | Not mostly black/frozen. | total = 0.0 |
| Non-degenerate audio | Not silent or heavily clipped. | total = 0.0 |
| Caption sidecar | `submit/captions.srt` exists and parses. | dimension B capped at 0.45 |
| Edit log parseable | `submit/edit_decision.json` valid JSON and schema-compatible. | dimension C capped at 0.65 |

## 10. Reward Vector

Verifier output:

```json
{
  "task_id": "rough_interview_caption_cleanup",
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
    "captions_srt_valid": true,
    "edit_decision_valid": true
  },
  "dimensions": {
    "speech_cleanup_semantic_preservation": 0.0,
    "caption_audio_deliverable_quality": 0.0,
    "source_fidelity_format_naturalness": 0.0
  },
  "hard_subscores": {
    "inserted_pause_removed_ratio": 0.0,
    "max_internal_silence_sec": 0.0,
    "repeat_loop_suppression": 0.0,
    "semantic_anchor_recall": 0.0,
    "caption_token_coverage": 0.0,
    "caption_timing_error_ms": 0.0,
    "caption_visibility": 0.0,
    "audio_quality": 0.0,
    "source_fidelity": 0.0,
    "format_compliance": 0.0,
    "edit_decision_consistency": 0.0
  },
  "llm_scores": {
    "semantic_completion": 0.0,
    "edit_naturalness": 0.0,
    "caption_readability": 0.0
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
      0.45 * speech_cleanup_semantic_preservation
    + 0.30 * caption_audio_deliverable_quality
    + 0.25 * source_fidelity_format_naturalness
```

Caps:

```text
if semantic_anchor_recall < 0.35:
    total <= 0.55
if inserted_pause_removed_ratio < 0.35:
    total <= 0.65
if source_fidelity < 0.50:
    total <= 0.30
if captions_srt is missing:
    total <= 0.75
if output contains > 4s continuous black/freeze/silence padding:
    total <= 0.50
```

## 11. Automation Boundary

| Check | Deterministic hard verifier | LLM judge | Human review |
| --- | --- | --- | --- |
| Format, streams, duration | yes | no | no |
| Black/frozen/silent degeneration | yes | no | no |
| Injected dead-air removal | yes | no | optional for calibration |
| Repeated-loop suppression | yes | no | optional for calibration |
| Semantic anchor preservation | mostly yes | yes for meaning tiebreaker | optional |
| Caption SRT timing | yes | no | no |
| Burned caption visibility | yes, heuristic | yes for readability | optional |
| Audio loudness/clipping/noise | yes | no | no |
| Edit naturalness | partial | yes | optional |

LLM judge evidence pack:

- public rough source contact sheet;
- output contact sheet;
- rough transcript excerpts around defects;
- output transcript and SRT excerpts;
- hard verifier summary;
- edit decision summary;
- two short before/after clips around the worst removed repeat/pause and a dense caption region.

LLM output:

```json
{
  "semantic_completion": 0.0,
  "edit_naturalness": 0.0,
  "caption_readability": 0.0,
  "major_failures": [],
  "rationale": ""
}
```

LLM score is capped at 20% influence and cannot override failed hard gates.

## 12. Hackability Analysis

| Scoring dimension | Cheat strategy | Classification | Detection / bound |
| --- | --- | --- | --- |
| Speech cleanup | Delete most content to remove all pauses/repeats. | Hackable but bounded | Duration, semantic anchor recall, source coverage, and LLM semantic score cap total. |
| Speech cleanup | Leave rough source unchanged. | Hard-to-hack | Injected pause/repeat map detects surviving defects. |
| Speech cleanup | Speed up the whole clip. | Hackable but bounded | Speech-rate, source-time compression, audio artifacts, and LLM naturalness penalties. |
| Caption/audio | Submit SRT but no burned captions. | Hackable but bounded | Visual caption-band sampling and LLM evidence catch missing burn-in. |
| Caption/audio | Add unrelated or prompt-like captions. | Hackable but bounded | SRT/output-ASR token overlap and timing checks fail. |
| Caption/audio | Mute or gate audio heavily. | Hard-to-hack | Non-silent gate, ASR collapse, RMS/loudness checks fail. |
| Source fidelity | Use unrelated interview/stock clip. | Hard-to-hack | Source frame/audio fingerprints fail. |
| Source fidelity | Fake `edit_decision.json`. | Hackable but bounded | Metadata is low weight and cross-checked against detected source segments. |
| Source fidelity | Pad with title card/still frames. | Hackable but bounded | Black/freeze/silence/source-fidelity checks cap total. |
| Source fidelity | Use leaked clean YouTube original. | Environment leakage, not reward hack | Prevent by hiding URL/reference and using no-network. A correct clean edit should score high if legitimately produced. |

## 13. Implementation Feasibility

CPU tools are sufficient:

- `ffmpeg`, `ffprobe`: probing, cutting, concat, subtitle burn-in, audio filters.
- `faster-whisper`: source/output transcripts.
- `librosa`, `soundfile`, `pydub`, `scipy`, `numpy`: silence, RMS, clipping, noise, phrase-loop detection.
- `opencv-python`, `Pillow`, `scikit-image`: frame sampling, black/freeze checks, caption-band heuristics.
- `jsonschema`, `pydantic`, `pandas`: schema validation and score reporting.

Calibration baselines:

| Baseline | Expected behavior |
| --- | --- |
| `copy_input` | Keeps inserted pauses/repeats; low cleanup score. |
| `silence_remove_only` | Removes pauses but may preserve repeats and damage semantics; medium-low. |
| `overtrim` | Clean but loses semantic anchors; capped total. |
| `no_captions` | Reasonable edit but caption dimension capped. |
| `oracle_defect_map` | High score if cuts/captions/audio are good. |

Implementation risk:

- CPU Whisper runtime can be slow, but source/output are short enough.
- Caption visibility heuristics are imperfect, so SRT timing plus LLM readability should share responsibility.
- Semantic preservation via anchors is not as hard as clean-reference sync scoring; keep LLM semantic judge as a small but meaningful tiebreaker.

## 14. Why This Is Good for Long-Horizon RL

This task has a real dependency chain: inspect media, transcribe, detect defects, choose a semantic
arc, edit around speech boundaries, normalize audio, generate captions, burn them in, render, verify,
and revise. It is not solved by one `silenceremove` command because a high-scoring output must
preserve the argument, suppress repeated phrase loops, produce aligned captions, and remain
source-faithful.

It also improves the benchmark portfolio:

```text
expert_pancake_vertical_short: visual/social source selection
piecewise_av_sync_repair: technical sync/damage repair
rough_interview_caption_cleanup: speech cleanup + captions + semantic preservation
```

Together these three tasks cover different editing workflows and reward surfaces while staying inside
the CPU-first tool environment.
