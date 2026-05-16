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

## Expected Workflow

You should usually:

1. Inspect the task prompt and materials.
2. Probe source media with `ffprobe`.
3. Extract or sample audio/frames when useful.
4. Build an edit plan.
5. Render a first output.
6. Verify duration, streams, resolution, audio presence, and visual sanity.
7. Revise if the output violates the task requirements.
8. Submit final artifacts.

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
edit plan you chose, major commands/scripts run, notable errors, fixes, and final self-checks.

`submit/agent_transcript.md` should preserve the useful transcript of your work session. Include
observable actions, commands, outputs, failures, revisions, and checks. Do not include hidden or
private chain-of-thought; summarize decisions rather than exposing private reasoning.

## Important

Do not submit only a plan or explanation. The benchmark is scored on the produced artifacts.

Do not intentionally game superficial checks such as output existence, duration, or black-frame padding. Preserve task-relevant content and follow the task-specific prompt.
