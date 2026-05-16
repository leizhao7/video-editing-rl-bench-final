# Worker 1-5 Task Review

Review date: 2026-05-16

Evaluation lens: the Philo take-home asks for long-horizon agentic RL tasks with clear horizon,
capability mix, difficulty gradient, per-task specs, automatable verifiers, explicit automation
boundary, dense reward vectors, and reward-hacking analysis. I reviewed workers 1-5 against those
standards and the CPU-first environment constraints.

## Summary Ranking

| Rank | Worker | Task | Overall | Reason |
| ---: | --- | --- | ---: | --- |
| 1 | worker_5 | Pancake Expert Vertical Short | 9.1/10 | Best mix of realistic editing, long-horizon source discovery, positive/negative ground truth, hard verifier potential, and reward-hack resistance. |
| 2 | worker_02 | Vertical Windsor Knot Tutorial Short | 8.7/10 | Very clean instructional task with strong step order and ROI verifier; slightly less long-horizon because source is short and focused. |
| 3 | worker_4 | Procrastination Story Vertical Short | 8.2/10 | Strong real social edit and transcript verifier; source is only 81s, so less selection pressure and more subjective storytelling. |
| 4 | worker_1 | Fluffy Pancake Vertical Recipe Short | 8.0/10 | Realistic and well-scoped, but stage matching is more brittle and less adversarial than worker_5. |
| 5 | worker_3 | Captioned Vertical Short From Filler-Words Tutorial | 7.6/10 | Good ASR/concept task, but mostly static talking-head editing makes visual grounding weaker. |

Selected task to improve: `worker_5`, "Pancake Expert Vertical Short".

## Criteria Scores

| Worker | Real Task | Horizon | Capability Mix | Hard Verifier | LLM Boundary | Hackability | Implementation Risk | Notes |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| worker_1 | 9 | 8 | 8 | 8 | 8 | 8 | 7 | Good cooking-to-reel task. Needs tighter source-match and caption checks because recipe scenes can look similar and source has existing overlays. |
| worker_02 | 9 | 8 | 9 | 9 | 8 | 9 | 8 | Very solid. Essential tie steps, hand/tie ROI, ASR keywords, and final knot checks are implementable. Weakness: source is short and low-res. |
| worker_3 | 8 | 8 | 7 | 8 | 8 | 8 | 8 | Strong transcript/concept coverage but visually too easy. The task may become mostly ASR + crop + captions. |
| worker_4 | 9 | 7 | 8 | 8 | 8 | 8 | 7 | Real social edit with good story rubric. But source is already a compact excerpt, so selection depth is lower. |
| worker_5 | 9 | 9 | 9 | 9 | 8 | 9 | 7 | Strongest RL shape: agent must identify expert material inside noisy challenge footage, avoid tempting negative clips, preserve cooking-step order, reframe, caption, and self-check. |

## Worker Notes

### worker_1: Fluffy Pancake Vertical Recipe Short

Strengths:

- Real creator workflow: turn a landscape recipe tutorial into a vertical recipe short.
- 12-step plan is appropriate.
- Strong public/private split and hard rewards for stage coverage, crop, captions, audio, and pacing.

Weaknesses:

- Preppy Kitchen is already a clean recipe tutorial, so the agent's main challenge is compression rather than discovery.
- Several cooking stages may be visually similar; source-stage matching can become brittle unless anchors are carefully annotated.
- Existing on-screen text can confuse caption-presence verification.

Verdict: good task, but less adversarial and less sensitive to agent quality than worker_5.

### worker_02: Vertical Windsor Knot Tutorial Short

Strengths:

- Very natural real-world task.
- Essential step order is clear and verifier-friendly.
- ROI verification for tie/hands/knot is concrete.
- Hard verifier is strong and mostly CPU-feasible.

Weaknesses:

- The source is only about two minutes and already instructional, so the horizon is not as deep as a messy-source task.
- Low-resolution source may make ROI and caption visual checks noisy after vertical upscaling.

Verdict: excellent candidate, probably easiest to implement robustly. I would keep it as one of the final three benchmark tasks.

### worker_3: Captioned Vertical Short From Filler-Words Tutorial

Strengths:

- Strong ASR/concept-coverage design.
- Realistic repurposing workflow.
- Good automation boundary: hard verifier handles format, source authenticity, concept coverage, pacing, crop, captions.

Weaknesses:

- Static talking-head source makes visual/frame analysis less meaningful.
- Face-safe crop can be solved by a simple center crop for most frames.
- The task may over-index on transcript selection rather than multimodal video editing.

Verdict: useful if you need a speech-heavy task, but not the best representative video-editing RL environment.

### worker_4: Procrastination Story Vertical Short

Strengths:

- Real social editing task from a TED excerpt.
- Story beat preservation is well designed.
- Dynamic reframe between speaker and slides is a meaningful visual challenge.
- Good pause/laughter cleanup dimension.

Weaknesses:

- Source is only 81 seconds, target is 58-66 seconds. The agent can pass by trimming modestly, captioning, and reframing.
- Story quality leans more on LLM judge than the best hard-verifier tasks.

Verdict: strong task, but better as a subjective/storytelling task than the single best first implementation.

### worker_5: Pancake Expert Vertical Short

Strengths:

- Realistic enough: a social editor repurposes a noisy challenge video into a practical tutorial.
- Excellent RL shape: source inspection -> identify positive expert segment -> reject negative novice footage -> preserve ordered steps -> vertical reframe -> captions/audio -> self-check.
- Positive intervals and negative intervals create hard-to-hack reward dimensions.
- Verifier can compute dense subscores from final media rather than trusting edit logs.
- Good sensitivity to policy quality: weak agents may use funny novice clips or one easy expert span; strong agents will recover the full recipe sequence.

Weaknesses to improve:

- The task prompt should be stricter about whether novice clips are allowed. For the benchmark, disallow novice clips except incidental source overlap under a small threshold.
- Positive/negative intervals must be manually locked during package generation; the current report marks them as approximate.
- Reframe scoring should use manually annotated ROIs over positive intervals, not only generic "active cooking content" heuristics.
- Caption verifier should separate visual caption presence from caption semantic accuracy; the latter belongs mostly to LLM judge.
- Add a cap rule so a submission with high negative-material leakage cannot score high overall.

Verdict: best task to improve and implement first.

## Selected Task

The improved task spec is written in:

```text
tasks/selected_pancake_expert_vertical_short.md
```

