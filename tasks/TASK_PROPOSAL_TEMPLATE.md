# <Task Name>

## 1. Metadata

- Worker ID:
- Task slug:
- Task family:
- Proposed difficulty: easy / medium / hard
- Expected semantic steps:
- Expected agent runtime:
- Primary editing capabilities tested:

## 2. YouTube Source Videos

List at least 3 candidate videos and select 1 primary source.

| Role | URL | Channel/title | Clip start | Clip end | Why this clip fits | Risks |
| --- | --- | --- | --- | --- | --- | --- |
| Primary |  |  |  |  |  |  |
| Backup 1 |  |  |  |  |  |  |
| Backup 2 |  |  |  |  |  |  |

Required provenance fields for the primary source:

```json
{
  "source": "youtube",
  "url": "",
  "video_id": "",
  "title": "",
  "channel": "",
  "clip_start_sec": 0.0,
  "clip_end_sec": 0.0,
  "estimated_duration_sec": 0.0,
  "downloaded_filename": "source.mp4",
  "notes": ""
}
```

## 3. Task Prompt Draft

Write the user-facing task prompt that the editing agent would receive.

```text

```

## 4. Long-Horizon Step Plan

Break the task into 8-15 semantic steps. Count editing decisions, not shell commands.

| Step | Required decision/action | Expected tools/libraries | Observable output |
| --- | --- | --- | --- |
| 1 |  |  |  |
| 2 |  |  |  |
| 3 |  |  |  |
| 4 |  |  |  |
| 5 |  |  |  |
| 6 |  |  |  |
| 7 |  |  |  |
| 8 |  |  |  |

## 5. Capabilities Tested

Explain which capabilities this task evaluates and why the selected source video makes them non-trivial.

- Metadata probing:
- Audio analysis:
- Visual/frame analysis:
- Edit planning:
- Rendering/export:
- Self-check/iteration:
- Optional semantic judgment:

## 6. Public Materials

List the files the agent should see.

```text
materials/
  source.mp4
  prompt.md
  tools.md
```

Add any proposed public sidecars, such as transcript snippets, style notes, target duration, or
allowed output formats.

## 7. Hidden Ground Truth / Private Materials

List private files used by the verifier only.

```text
private/
  ground_truth.json
  verifier_config.json
```

Explain what each private field stores and how it will be generated.

## 8. Hard Verifier Design

Hard verifier should validate objective properties from the final output video, not trust the
agent's edit log.

### 8.1 Mandatory Gates

| Gate | Method | Failure behavior |
| --- | --- | --- |
| Output exists |  |  |
| ffprobe readable |  |  |
| Has required streams |  |  |
| Duration valid |  |  |
| Resolution/aspect valid |  |  |
| Non-black/non-frozen |  |  |
| Non-silent/non-clipped audio |  |  |
| edit_decision.json schema valid |  |  |

### 8.2 Dense Hard Rewards

Weights should sum to 1.0 inside the hard verifier section.

| Reward ID | Weight | What it measures | Inputs | Calculation method | Full-credit threshold | Partial-credit curve | Anti-hack check |
| --- | ---: | --- | --- | --- | --- | --- | --- |
| hard_1 |  |  |  |  |  |  |  |
| hard_2 |  |  |  |  |  |  |  |  |
| hard_3 |  |  |  |  |  |  |  |  |
| hard_4 |  |  |  |  |  |  |  |  |

## 9. LLM Judge Design

LLM judge should only evaluate semantic or aesthetic properties that hard metrics cannot measure
reliably.

### 9.1 Evidence Pack

Describe exactly what compact evidence is shown to the judge.

- Source contact sheet:
- Output contact sheet:
- Source transcript excerpt:
- Output transcript excerpt:
- edit_decision.json summary:
- Hard verifier summary:
- Short before/after clips, if needed:

### 9.2 Judge Rubric

Weights should sum to 1.0 inside the LLM judge section.

| LLM Reward ID | Weight | Question asked to judge | Score scale | Failure examples |
| --- | ---: | --- | --- | --- |
| llm_1 |  |  |  |  |
| llm_2 |  |  |  |  |
| llm_3 |  |  |  |  |

Expected structured output:

```json
{
  "semantic_completion": 0.0,
  "continuity": 0.0,
  "naturalness": 0.0,
  "major_failures": [],
  "rationale": ""
}
```

## 10. Final Score Formula

Specify the score formula.

```text
if any mandatory gate fails:
    total = gate_failure_score
else:
    total = hard_weight * hard_score + llm_weight * llm_score + metadata_weight * metadata_score
```

Recommended default:

```text
hard_weight = 0.70
llm_weight = 0.20
metadata_weight = 0.10
```

## 11. Reward Hacking Analysis

List at least 5 plausible cheating or degenerate strategies and how the verifier catches them.

| Hack | Why agent might try it | Detection / penalty |
| --- | --- | --- |
|  |  |  |
|  |  |  |
|  |  |  |
|  |  |  |
|  |  |  |

## 12. Implementation Feasibility

Explain how this can be implemented with the CPU-first environment.

- Required shell tools:
- Required Python packages:
- Estimated verifier complexity:
- Biggest implementation risk:
- Suggested simplification if too hard:

## 13. Why This Is Good for Long-Horizon RL

Explain why the task requires planning, intermediate inspection, iterative correction, and
multi-step tool use rather than one simple command.

