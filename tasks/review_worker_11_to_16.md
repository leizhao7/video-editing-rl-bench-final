# Worker 11-16 Task Review

Review date: 2026-05-16

Evaluation lens: Philo take-home requirements: long-horizon decision structure, capability mix,
difficulty gradient, self-contained task package, verifier quality, automation boundary, dense reward
shape, and reward-hacking resistance. I also checked overlap against the two already selected task
directions:

- `expert_pancake_vertical_short`: semantic source selection from noisy material into a social edit.
- `piecewise_av_sync_repair`: technical local A/V sync and damage repair.

## Summary Ranking

| Rank | Worker | Task | Overall | Decision | Reason |
| ---: | --- | --- | ---: | --- | --- |
| 1 | worker_13 | Polished Captioned Interview Short | 8.8/10 | Select and improve | Best new capability axis: speech cleanup, repeated-phrase/dead-air removal, transcript preservation, caption timing, audio polish. |
| 2 | worker_16 | Desynced Drum Lesson Short | 8.0/10 | Do not select now | Strong source and objective drum-hit sync signals, but it collides with the selected A/V repair task. |
| 3 | worker_14 | Piecewise A/V Sync Creator Tip | 7.8/10 | Do not select | Good verifier, but directly duplicates selected worker 7. |
| 4 | worker_11 | Vertical A/V Sync Repair Tutorial | 7.2/10 | Do not select | Constant-offset sync + vertical short; easier and less distinct than selected worker 7. |
| 5 | worker_15 | French Omelette Micro-Tutorial | 6.9/10 | Do not select | Solid but overlaps with prior cooking/tutorial vertical tasks. |
| 6 | worker_12 | Vertical Omelette Recipe Short | 6.7/10 | Do not select | Good standard tutorial-short spec, but too close to worker 5/6/9/15. |

Selected task to improve:

```text
worker_13: Polished Captioned Interview Short
```

Improved spec:

```text
tasks/selected_rough_interview_caption_cleanup.md
```

## Criteria Scores

| Worker | Real Task | Horizon | Capability Mix | Distinct From 5/7 | Hard Verifier | LLM Boundary | Hackability | Implementation |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| worker_11 | 8 | 8 | 7 | 3 | 8 | 8 | 8 | 8 |
| worker_12 | 8 | 8 | 7 | 3 | 7 | 7 | 7 | 8 |
| worker_13 | 9 | 8 | 8 | 9 | 8 | 8 | 8 | 8 |
| worker_14 | 9 | 9 | 8 | 2 | 9 | 8 | 8 | 7 |
| worker_15 | 8 | 8 | 7 | 3 | 7 | 7 | 7 | 8 |
| worker_16 | 9 | 9 | 8 | 5 | 8 | 8 | 8 | 7 |

## Worker Notes

### worker_11: Vertical A/V Sync Repair Tutorial Short

Strengths:

- Real creator workflow.
- Good use of private injected constant offset.
- Includes vertical reframe, captions, audio cleanup, and schema.

Weaknesses:

- Collides with the selected A/V repair task.
- Constant offset is easier than selected worker 7's piecewise local repair.
- Adds vertical/caption work, but the core capability is still sync repair.

Verdict: reject for portfolio diversity.

### worker_12: Vertical Omelette Recipe Short

Strengths:

- Realistic social editing task.
- Step coverage, crop safety, caption, and audio verifier are plausible.

Weaknesses:

- Directly repeats the cooking/tutorial vertical-short pattern.
- Does not add enough beyond worker 5's stronger positive/negative expert extraction task.

Verdict: reject.

### worker_13: Polished Captioned Interview Short

Strengths:

- Distinct capability axis: speech editing and captioning rather than cooking/social reframe or A/V repair.
- Uses a roughened public source with private dead-air/repeated-phrase/noise defect map, giving strong hard-verifier hooks.
- Natural real task: interview/social clips often need dead-air removal, repeat cleanup, captions, loudness cleanup, and concise semantic preservation.
- Verifier has good ingredients: pause removal, repeated-loop suppression, transcript anchor recall, subtitle timing, visual caption presence, audio quality, source fidelity.

Weaknesses to improve:

- The hard rewards should be grouped into 1-3 top-level dimensions with clear level definitions, as the PDF asks.
- It needs a clearer task generator and no-network/private-source leakage policy.
- The current "download the original YouTube clip" hack should be framed as environment leakage, not as a reason to penalize a clean-reference-quality output.
- Visual grounding is weaker than the other tasks, so subtitle visibility and source-video integrity need to carry some of the video-specific signal.

Verdict: best worker 11-16 proposal and a good candidate for the third benchmark task after improvement.

### worker_14: Piecewise A/V Sync Creator Tip

Strengths:

- Strong technical repair task.
- Good private clean-reference scoring.
- Good hard verifier design for local sync residuals.

Weaknesses:

- Too close to the selected `piecewise_av_sync_repair`.
- Would make the benchmark over-weight sync repair.

Verdict: reject for portfolio diversity, despite high quality.

### worker_15: French Omelette Micro-Tutorial

Strengths:

- Clean source, clear beats, realistic social edit.
- Reasonable hard verifier with visual beat coverage and label visibility.

Weaknesses:

- Another cooking/tutorial-to-vertical task.
- Lower-resolution source adds implementation risk without adding new capabilities.

Verdict: reject.

### worker_16: Desynced Drum Lesson Short

Strengths:

- Strong real-world source idea: drum hits provide measurable visual/audio transients.
- More dynamic crop challenge than talking-head sync.
- Could be a good task in a different portfolio.

Weaknesses:

- Still overlaps with the selected A/V sync repair task.
- Combines sync + vertical reframe + captions, but the highest-value novelty is sync residual scoring, which is already covered.

Verdict: runner-up, but do not select unless replacing worker 7.

## Recommended Portfolio After This Review

| Slot | Task | Capability Axis |
| --- | --- | --- |
| 1 | `expert_pancake_vertical_short` | semantic source selection, positive/negative intervals, social repurposing |
| 2 | `piecewise_av_sync_repair` | technical diagnosis, local A/V repair, damage cleanup |
| 3 | `rough_interview_caption_cleanup` | speech cleanup, repeated-phrase/dead-air removal, subtitle timing, audio polish |

This gives a cleaner capability mix than choosing another tutorial-to-vertical or sync-repair task.
