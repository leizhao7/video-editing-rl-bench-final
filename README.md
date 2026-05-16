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

submissions/
  <agent>/<task_id>/
    output.mp4            # agent-produced artifact
    run_log.json          # command/session metadata

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

## Intended Commands

```bash
vebench generate --task all
vebench run --agent codex --task silence_filler_trim
vebench verify --agent codex --task silence_filler_trim
vebench report
```

The CLI implementation is intentionally thin in this scaffold; fill in each task package first, then
wire it into the registry.
