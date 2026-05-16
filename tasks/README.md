# Benchmark Tasks

This folder contains only the formal benchmark task packages used by `vebench`.

```text
tasks/
  expert_pancake_vertical_short/
  piecewise_av_sync_repair/
  rough_interview_caption_cleanup/
```

Each task has a public package copied into agent workspaces:

```text
public/
  prompt.md
  tools.md
  source_metadata.json
  output_specs.json
  edit_decision.schema.json
  materials/source.mp4        # generated locally, ignored by git
```

Every run should write final artifacts under `submit/`, including `output.mp4`,
`edit_decision.json`, `run_history.md`, and `agent_transcript.md` (plus task-specific files such as
`captions.srt` when requested). Raw runner logs are stored separately under the run workspace's
`_logs/` directory.

Private verifier files live under `private/` and are ignored by git because they may include
ground truth, private references, ROI annotations, and generated media.

Worker proposal folders and selection notes are intentionally not kept here; the benchmark repo
should expose the final runnable tasks rather than the task-design scratch space.
