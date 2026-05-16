# Video Editing RL Mini-Benchmark

This repo is a scaffold for a 3-task video-editing benchmark for long-horizon agentic RL.

The benchmark shape is:

```text
task generator -> agent execution -> verifier scoring -> aggregate report
```

The intended first deployment is a CPU video-editing server: `ffmpeg`, `ffprobe`, Python 3.11, and
analysis libraries run locally; heavyweight AI/video models can be replaced with APIs or omitted.

## Repo Layout

```text
src/vebench/
  cli.py                  # single entrypoint for generate/run/verify/report
  media/                  # ffmpeg, ffprobe, audio/video helper wrappers
  tasks/                  # task registry and task generator implementations
  verifiers/              # scorer implementations and shared metric code
  agents/                 # wrappers for Codex/Claude/Gemini/OpenCode/manual runs
  reporting/              # tasks_and_rubrics.tsv and LaTeX report helpers

prompts/
  general_agent_prompt.md # shared instructions prepended to every agent task
  tools_cpu.md            # CPU sandbox tool reference copied into each run

tasks/
  <task_id>/
    prompt.md             # prompt given to the agent
    materials/            # source media and sidecar files
    ground_truth.json     # hidden or verifier-only scoring data
    rubric.yaml           # scoring dimensions + hackability notes

runs/
  <run_id>/workspace/
    submit/output.mp4              # agent-produced video
    submit/edit_decision.json      # machine-readable edit record
    submit/run_history.md          # chronological action log
    submit/agent_transcript.md     # useful session transcript or transcript summary
    _logs/runner_command.json      # Docker invocation metadata
    _logs/runner_result.json       # return code and runtime metadata
    _logs/docker_stdout_stderr.log # raw runner stdout/stderr
    _logs/native_sessions/         # copied Codex/Claude native session files when available

Agent CLI credentials and native session stores persist outside the ephemeral Docker container under
`$VEBENCH_AGENT_HOME_ROOT/<agent>/`, defaulting to `~/.vebench-agent-home/<agent>/` on the host.

reports/
  tasks_and_rubrics.tsv   # generated benchmark table

report/
  main.tex                # take-home writeup source
```

See [docs/repo_framework.md](docs/repo_framework.md) for the design rationale and
[docs/task_specs.md](docs/task_specs.md) for the proposed three-task benchmark.

## Server Bootstrap

On an Ubuntu 22.04 server:

```bash
bash scripts/bootstrap_ubuntu.sh
python3.11 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e .
```

If the server has a large data disk, set:

```bash
export VEBENCH_DATA_ROOT=/data/video-agent
export TMPDIR=/data/video-agent/tmp
```

## Implemented Tasks

The first implementation pass wires the three selected task designs into the CLI:

```text
expert_pancake_vertical_short       # worker 5: expert tutorial extraction from noisy challenge video
piecewise_av_sync_repair            # worker 7: local A/V sync and damage repair
rough_interview_caption_cleanup     # worker 13: speech cleanup, captions, and interview polish
```

Task packages can be generated as metadata-only scaffolds, or with a local source video:

```bash
vebench generate --task all
vebench generate --task expert_pancake_vertical_short --source /path/to/pancake_source.mp4 --force
vebench generate --task piecewise_av_sync_repair --source /path/to/clean_clap_source.mp4 --force
vebench generate --task rough_interview_caption_cleanup --source /path/to/clean_interview_source.mp4 --force
```

`--source` should be the downloaded source video for that task. For task 7 and task 13, the
generator creates the public damaged/rough `materials/source.mp4` and stores private references or
defect maps under `tasks/<task_id>/private/`.

For task 5, generate private ROI annotations after packaging the real source:

```bash
export OPENAI_API_KEY=...
vebench annotate-roi --task expert_pancake_vertical_short --model gpt-5.5 --frames-per-step 3
```

This writes `tasks/expert_pancake_vertical_short/private/roi_keyframes.json`. The verifier then
checks whether LLM-annotated source ROIs such as pancake, pan, hand, spatula, and plated result are
still visible in the submitted vertical crop.

## Intended Commands

```bash
vebench generate --task all
vebench prepare --agent codex --task expert_pancake_vertical_short
vebench run --run-id expert_pancake_vertical_short-codex --model gpt-5.5
vebench verify --run-id expert_pancake_vertical_short-codex
vebench verify --run-id expert_pancake_vertical_short-codex --llm-judge --llm-model gpt-5.5
vebench report
```

Verifier status: this is a v1 hard-verifier implementation. It enforces media gates, format,
duration/aspect, non-degenerate audio/video, JSON schema, SRT/caption checks, crop-aware
output-to-source visual matching, source interval coverage, negative/defect interval leakage,
private clean-reference A/V residuals for the sync task, and private rough-source defect regions for
the interview task. For the interview task it also runs `faster-whisper` on the output when
available, caches `_logs/output_asr.json`, and scores token-level semantic anchor recall, anchor
order, and duplicate n-gram rate. It also checks that each run saves `submit/run_history.md` and
`submit/agent_transcript.md`; Docker runs additionally keep raw CLI/runner logs under `_logs/`.
Codex and Claude Code native session stores are snapshotted before the container exits when their
standard session directories are present.

LLM-as-judge is optional at verify time because it calls the OpenAI API. Set `OPENAI_API_KEY` and run
with `--llm-judge`; the default judge model is `gpt-5.5`. If the judge is unavailable, the verifier
keeps the hard-verifier score and records a note. When enabled, the LLM score contributes 20% as a
tiebreaker and cannot override failed hard gates.

Known verifier limitations: ROI containment becomes much stronger after running `annotate-roi`, but
the private boxes are still LLM/VLM-generated labels rather than human labels. Source matching is CPU
feature matching rather than a learned video retrieval model, so thresholds should be calibrated on
the real YouTube packages.
