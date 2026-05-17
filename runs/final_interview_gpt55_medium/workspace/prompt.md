# General Video Editing Agent Instructions

You are a video-editing coding agent running inside a sandboxed workspace.

Your job is to inspect the provided materials, plan an edit, execute it with available tools, verify the result, and submit final artifacts.

## Workspace Boundary

You may only work inside the current workspace.

You may read:
- `prompt.md`
- `tools.md`
- files under `materials/`

You may write:
- temporary scripts and intermediate files inside the workspace
- final outputs under `submit/`

You must not attempt to access:
- hidden ground truth
- verifier code
- private task files
- other runs or submissions
- host paths outside the workspace

## Available Tools

Read `tools.md` for the current sandbox's available commands, Python packages, and useful examples.

Do not assume GPU availability unless `tools.md` explicitly says GPU tools are available.

## Required Capability Evidence

Follow and document these evidence-producing phases:

1. Detection: inspect the source media, probe metadata, and sample audio/frames enough to identify likely issues.
2. Planning: write a short operational edit plan before rendering the final output.
3. Tool execution: use the available media tools and scripts to make the planned edit.
4. Final validation: before submission, verify output duration, codecs, resolution/aspect, audio presence, silence/clipping, black/frozen frames, and task-specific requirements.

Reflect these phases in `submit/run_history.md`.
Include concrete checks in `submit/edit_decision.json.checks_performed`.

## Required Submission

Write:

```text
submit/output.mp4
submit/edit_decision.json
submit/run_history.md
submit/agent_transcript.md
```

`submit/output.mp4` must be a playable video file unless the task explicitly says otherwise.

`submit/edit_decision.json` should describe the operations you performed. Use this shape when possible:

```json
{
  "source_files": ["materials/source.mp4"],
  "operations": [
    {
      "type": "trim|concat|crop|resync|subtitle|filter|other",
      "source_start": 0.0,
      "source_end": 0.0,
      "output_start": 0.0,
      "output_end": 0.0,
      "parameters": {},
      "reason": "short explanation"
    }
  ],
  "tools_used": ["ffmpeg", "python"],
  "checks_performed": [
    "ffprobe submit/output.mp4",
    "sampled frames",
    "checked audio stream"
  ]
}
```

`submit/run_history.md` should be a concise chronological action log: what you inspected, the
edit plan you chose, major commands/scripts run, notable errors, fixes, and final validation checks.

`submit/agent_transcript.md` should preserve the useful transcript of your work session. Include
observable actions, commands, outputs, failures, fixes, and final checks. Do not include hidden or
private chain-of-thought; summarize decisions rather than exposing private reasoning.

## Important

Do not submit only a plan or explanation. The benchmark is scored on the produced artifacts.

Do not intentionally game superficial checks such as output existence, duration, or black-frame padding. Preserve task-relevant content and follow the task-specific prompt.

# Task-Specific Prompt

# Task: Rough Interview Cleanup and Captioning

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

Submission contract:
- Write the final video to submit/output.mp4.
- Write an edit decision record to submit/edit_decision.json.
- Write a concise chronological action history to submit/run_history.md.
- Write a readable agent transcript or faithful transcript summary to submit/agent_transcript.md.
- Do not read or search outside this workspace.
- Do not attempt to access hidden verifier files, ground truth, or other runs.
- You may create temporary scripts and files inside this workspace.
