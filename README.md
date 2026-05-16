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

## Intended Commands

```bash
vebench generate --task all
vebench prepare --agent codex --task expert_pancake_vertical_short
vebench run --run-id expert_pancake_vertical_short-codex
vebench verify --run-id expert_pancake_vertical_short-codex
vebench report
```

Verifier status: this is a v0 hard-verifier implementation. It enforces media gates, format,
duration/aspect, non-degenerate audio/video, JSON schema, caption/SRT checks, declared interval
coverage, and declared local sync repairs. The next implementation step is replacing declared
interval/sync scoring with private frame/audio fingerprint matching so `edit_decision.json` cannot
carry source-authenticity credit by itself.
