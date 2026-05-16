# Worker 6-10 Homogeneity Review

Review date: 2026-05-16

Question: are worker 6-10 task proposals too homogeneous in topic and capability coverage?

Short answer: yes. Workers 6, 8, 9, and 10 are all variations of the same benchmark pattern:

```text
longer horizontal tutorial -> select ordered steps -> trim -> vertical reframe -> add captions/labels
-> normalize audio -> export -> validate
```

Only worker 7 is genuinely different.

## High-Level Ranking

| Rank | Worker | Task | Keep? | Why |
| ---: | --- | --- | --- | --- |
| 1 | worker_7 | Piecewise A/V Sync Repair | Yes | The only task with a distinct repair workflow: diagnose local offsets, remove black/freeze damage, preserve content, normalize audio, verify sync residuals. |
| 2 | worker_10 | Juggling Drill Vertical Short | Maybe, but rewrite | Still a tutorial short, but high-motion crop containment for balls/hands is more distinctive than static cooking/tie tasks. |
| 3 | worker_9 | Vertical Omelette Tutorial Short | Probably no | Good visual landmark task, but overlaps heavily with pancake/cooking shorts. |
| 4 | worker_8 | Full Windsor Vertical Tutorial Short | Probably no | Strong verifier, but duplicates worker_02's Windsor-knot task. |
| 5 | worker_6 | Pancake Tutorial to Vertical Recipe Short | No | Too close to worker_1 and the already selected worker_5 pancake task. |

## Capability Matrix

| Capability | worker_6 pancake | worker_7 A/V repair | worker_8 Windsor | worker_9 omelette | worker_10 juggling |
| --- | --- | --- | --- | --- | --- |
| Metadata probing | yes | yes | yes | yes | yes |
| Source inspection/contact sheets | yes | yes | yes | yes | yes |
| Transcript/ASR use | yes | optional | yes | light/optional | yes |
| Semantic segment selection | yes | limited | yes | yes | yes |
| Ordered step coverage | yes | content span preservation | yes | yes | yes |
| Positive/negative interval discrimination | weak | damage/reference based | yes, target vs neighboring knot sections | weak | weak |
| Vertical 9:16 reframing | yes | no | yes | yes | yes |
| Dynamic/motion-safe crop | mild | no | mild | medium | strong |
| Caption/label burn-in | yes | no | yes | yes | yes |
| Audio normalization | yes | yes | yes | yes | yes |
| A/V sync diagnosis | no | yes, core | no | no | no |
| Damage repair | no | yes, core | no | no | no |
| Clean-reference scoring | no | yes | no | no | no |
| Hard verifier novelty | low | high | medium | medium | medium |

## Repeated Pattern

Workers 6, 8, 9, and 10 all rely on the same verifier skeleton:

1. `format/duration`: ffprobe checks for duration, codec, aspect, fps.
2. `source authenticity`: pHash/SSIM/ORB/MFCC matching back to the source.
3. `step or landmark coverage`: required ordered windows must appear.
4. `vertical ROI/action containment`: object or subject must remain visible in 9:16 crop.
5. `caption/label presence`: text-like overlay or caption sidecar checks.
6. `audio quality`: RMS, clipping, silence, loudness.
7. `edit_decision.json` consistency.

That is a good verifier pattern, but four copies of it will make the benchmark feel narrow. It mostly
tests the same agent abilities:

- can the agent inspect a long source?
- can it choose instructional steps?
- can it make a vertical social short?
- can it add captions?
- can it pass media-format checks?

The surface topics differ, but the underlying policy skill is nearly the same.

## Worker-Specific Notes

### worker_6: Pancake Tutorial to Vertical Recipe Short

This is a good task in isolation but should be rejected for this benchmark set. It overlaps directly
with worker_1 and the selected worker_5 pancake task. It lacks worker_5's strongest feature:
positive expert intervals versus negative novice/blooper intervals.

Capability profile:

- Strong: standard recipe stage coverage, crop containment, captions, audio.
- Weak: no distinctive new capability beyond selected pancake task.
- Recommendation: do not use.

### worker_7: Piecewise A/V Sync Repair

This is the standout proposal. It is not "tutorial-to-short"; it is a repair task. The hard verifier is
also much more RL-relevant because it can compare final media against a private clean reference and
corruption recipe.

Distinct capabilities:

- Diagnose local A/V offset, not just one global offset.
- Remove black leader/tail and freeze/dead-air splice.
- Repair with piecewise audio shifts.
- Preserve required content in order.
- Score residual sync error with audio/video matching against a clean reference.
- Detect destructive speed hacks and padding.

Recommendation: keep and improve as one of the final 3 tasks.

### worker_8: Full Windsor Vertical Tutorial Short

This is solid but overlaps with worker_02 almost exactly. It adds a useful target-window vs
neighboring-knot negative-window design, but worker_02 already covers a tie tutorial with ROI,
step coverage, captions, and audio.

Capability profile:

- Strong: ordered procedural steps, target/negative section discrimination, ROI for tie/hands.
- Weak: not meaningfully different from worker_02.
- Recommendation: do not use if worker_02 is already a candidate.

### worker_9: Vertical Omelette Tutorial Short

This has a nice visual verifier idea: yellow/cream HSV masks and cooking landmark coverage. But
the benchmark already has pancake/cooking tasks, so this would make the set feel too food-heavy.

Capability profile:

- Strong: visual landmark coverage and food-action crop checks.
- Weak: same recipe-short flow as worker_1/5/6.
- Recommendation: skip unless you specifically want a visually rich cooking variant.

### worker_10: Juggling Drill Vertical Short

This is still a tutorial short, but it is the least redundant among the vertical-short tasks because
the core visual risk is high-motion crop containment. A naive 9:16 center crop will cut off the balls.
That makes it closer to action/sports reframing than cooking/tutorial summarization.

Capability profile:

- Strong: dynamic motion-safe crop, ordered progression one-ball -> two-ball -> three-ball,
  action containment, pacing.
- Weak: still uses the same trim/reframe/caption/audio/export skeleton.
- Recommendation: either skip, or rewrite it away from "captioned tutorial short" into a dynamic
  action-reframing task with a stronger tracking/crop verifier.

## What This Means for the Final Benchmark

For the final 3 tasks, avoid selecting more than one plain "tutorial to vertical short" task.

Best current portfolio:

| Slot | Task | Why |
| --- | --- | --- |
| 1 | Selected worker_5 pancake expert extraction | Tests source discovery, positive/negative interval discrimination, ordered recipe coverage, vertical reframe, captions. |
| 2 | worker_7 piecewise A/V sync repair | Tests repair, local offset diagnosis, clean-reference scoring, damage cleanup, audio/video preservation. |
| 3 | rewritten worker_10 action-reframe task, or a new non-tutorial task | Adds dynamic subject/action containment and motion-safe cropping without another food/tie tutorial. |

Avoid this portfolio:

```text
pancake short + Windsor short + omelette short
```

It would look like three different topics, but it would really be the same eval three times.

## Recommended Rewrite for worker_10

If keeping worker_10, change the task from:

```text
make a captioned vertical juggling tutorial
```

to:

```text
make a motion-safe vertical demonstration reel from a juggling tutorial
```

The rewritten task should reduce transcript/caption dependence and emphasize:

- track high-motion balls/hands through the frame;
- create a crop path that keeps the full throw arc visible;
- choose demonstrations with successful throws, not long talk sections;
- preserve one-ball, two-ball, and three-ball progression;
- verify action containment with HSV/optical-flow/private safe boxes;
- penalize center crops that cut off balls;
- make captions optional or low-weight.

That would make it a more distinct third task.

## Bottom Line

Your instinct is right. The workers independently converged on the same "procedural tutorial short"
template because the prompt and tool stack naturally favor it: it is realistic, CPU-feasible, and easy
to verify with ordered stage windows. But for the take-home, the benchmark needs a capability mix
and difficulty gradient, not five flavors of the same task.

Keep worker_7. Keep at most one of the vertical tutorial shorts. If you want a third task from this
batch, rewrite worker_10 into a motion/action reframing task rather than another captioned tutorial.

