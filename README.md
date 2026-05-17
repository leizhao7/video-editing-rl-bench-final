# Video Editing RL Benchmark

This repository contains a compact long-horizon video-editing benchmark for agentic coding systems. Each task is packaged as a folder with the public prompt and source media, private ground-truth criteria, verifier code, and hackability analysis. The pipeline prepares an isolated workspace, runs an agent in Docker, verifies the submitted edit, and aggregates the results into `reports/tasks_and_rubrics.tsv`.

The benchmark currently includes three implemented tasks and historical runs from Codex, Claude Code, and Gemini CLI. API keys and account credentials are intentionally not committed.

## Repository Layout

```text
src/vebench/
  cli.py                    # Typer CLI: generate, prepare, run, verify, report, doctor
  agents/docker_runner.py   # Docker runner for Codex, Claude Code, Gemini, and shell-smoke
  tasks/                    # task registry and task package generation
  verifiers/                # hard verifiers and optional LLM-as-judge
  reporting/aggregate.py    # builds reports/tasks_and_rubrics.tsv
  media/                    # ffmpeg, ffprobe, audio/video/caption helpers

tasks/
  piecewise_av_sync_repair/
  expert_pancake_vertical_short/
  rough_interview_caption_cleanup/
    public/                 # prompt, tools, source metadata, output specs, schemas, materials
    private/                # ground truth, verifier config, hackability analysis

prompts/
  general_agent_prompt.md   # shared agent instructions
  tools_cpu.md              # sandbox tool reference

scripts/
  bootstrap_ubuntu.sh       # host dependency bootstrap
  build_agent_image.sh      # Docker image build
  run_final_matrix.sh       # one-command task x agent/model run + verify + report
  demo_one_task_pipeline.sh # small end-to-end smoke/demo pipeline

configs/
  final_model_matrix.tsv    # final 3-task x 8-model run matrix

runs/                       # historical run metadata, submissions, logs, and scores
reports/
  tasks_and_rubrics.tsv     # auto-generated deliverable table
report/
  main.tex
  video_editing_rl_benchmark_report.pdf
```

## Clone and Environment Setup

```bash
git clone https://github.com/leizhao7/video-editing-rl-bench-final.git
cd video-editing-rl-bench-final

bash scripts/bootstrap_ubuntu.sh
python3.11 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e .

bash scripts/build_agent_image.sh
python -m vebench.cli doctor
```

The benchmark assumes `ffmpeg`, `ffprobe`, Docker, Python 3.11+, and the Python packages from `pyproject.toml`. The Docker image used by default is `video-bench-agent:cpu`.

## Keys and Agent Login

Do not commit real keys. Put them in your shell environment or an untracked `.env` file.

```bash
export OPENAI_API_KEY=...       # Codex API mode and/or LLM judge
export ANTHROPIC_API_KEY=...    # Claude Code API mode
export GEMINI_API_KEY=...       # Gemini CLI API mode
```

For OpenRouter-backed LLM judging:

```bash
export OPENAI_API_KEY=...                    # OpenRouter key
export OPENAI_BASE_URL=https://openrouter.ai/api/v1
export VEBENCH_LLM_API_STYLE=chat
export VEBENCH_LLM_JUDGE_MODEL=gpt-5.5
```

Codex and Claude Code can also be used with account login instead of API keys. The Docker runner mounts persistent host homes under `~/.vebench-agent-home/<agent>/`, so login once and reuse:

```bash
mkdir -p ~/.vebench-agent-home/codex ~/.vebench-agent-home/claude

docker run --rm -it \
  -v ~/.vebench-agent-home/codex:/agent-home \
  -e HOME=/agent-home video-bench-agent:cpu \
  bash -lc 'codex login --device-auth'

docker run --rm -it \
  -v ~/.vebench-agent-home/claude:/agent-home \
  -e HOME=/agent-home video-bench-agent:cpu \
  bash -lc 'claude login'
```

Gemini CLI is normally run with `GEMINI_API_KEY`.

## One-Command Final Matrix

The final matrix is defined in `configs/final_model_matrix.tsv`. It covers the three tasks and eight model settings:

- GPT-5.5, GPT-5.4, GPT-5.4 Mini through Codex
- Claude Opus 4.7, Claude Sonnet 4.6, Claude Haiku 4.5 through Claude Code
- Gemini 3.1 Pro Preview and Gemini 3.1 Flash-Lite through Gemini CLI

Run the full matrix and verify each submission:

```bash
source .venv/bin/activate
export VEBENCH_LLM_JUDGE=1
scripts/run_final_matrix.sh
```

The script performs:

```text
prepare -> run agent -> verify -> aggregate report
```

At the end it writes `reports/tasks_and_rubrics.tsv`. Set `TASK_FILTER=piecewise_av_sync_repair` or `AGENT_FILTER=codex` to run a subset. Set `VEBENCH_LLM_JUDGE=0` to run hard verifiers only.

## Running One Task Manually

Prepare a workspace:

```bash
python -m vebench.cli prepare \
  --agent codex \
  --task piecewise_av_sync_repair \
  --run-id sync-codex-gpt55
```

Run the agent:

```bash
python -m vebench.cli run \
  --run-id sync-codex-gpt55 \
  --model gpt-5.5 \
  --effort medium
```

Verify and aggregate:

```bash
python -m vebench.cli verify \
  --run-id sync-codex-gpt55 \
  --llm-judge \
  --llm-model "${VEBENCH_LLM_JUDGE_MODEL:-gpt-5.5}"

python -m vebench.cli report \
  --runs-dir runs \
  --output reports/tasks_and_rubrics.tsv
```

## Smoke Test

This checks the local package, Docker runner, verifier, and TSV aggregation without calling a paid model:

```bash
RUNS_DIR=/tmp/vebench-demo-runs \
REPORT_PATH=/tmp/vebench-demo-reports/tasks_and_rubrics.tsv \
TASK_ID=piecewise_av_sync_repair \
AGENT=shell-smoke \
scripts/demo_one_task_pipeline.sh
```

The smoke agent intentionally submits a trivial synthetic video, so the score is not meaningful; the goal is to test the pipeline.

## Deliverables

- Report PDF: `report/video_editing_rl_benchmark_report.pdf`
- LaTeX source: `report/main.tex`
- Auto-generated TSV: `reports/tasks_and_rubrics.tsv`
- Task packages: `tasks/<task_id>/`
- Agent prompts: `prompts/` and each `tasks/<task_id>/public/prompt.md`
- Historical runs: `runs/`

`tasks_and_rubrics.tsv` is reproducible from checked-in run score files with:

```bash
python -m vebench.cli report --runs-dir runs --output reports/tasks_and_rubrics.tsv
```

The TSV includes a `suspected_reward_hacking` flag and a `hackability_analysis_path` column. The full hackability analysis is not expanded inline in the TSV; it lives in each task package at `tasks/<task_id>/private/hackability_analysis.md`.

## Historical Runs and Outputs

Historical agent runs are stored under `runs/<run_id>/`. Each run folder contains:

```text
runs/<run_id>/
  run.json                         # run metadata: task id, agent, model, effort, workspace
  score.json                       # verifier output for that run
  workspace/
    prompt.md                      # exact prompt given to the agent for this run
    tools.md                       # tool description copied into the workspace
    materials/source.mp4           # source video visible to the agent
    submit/
      output.mp4                   # final edited video produced by the agent
      edit_decision.json           # submitted edit decision record
      run_history.md               # action history written or recovered for the run
      agent_transcript.md          # agent transcript summary or fallback transcript
      captions.srt                 # caption file, when required by the task
```

The main output video for a historical run is therefore always expected at `runs/<run_id>/workspace/submit/output.mp4` when that run produced a real submission. Aggregated per-run scores are in `runs/<run_id>/score.json`, and the cross-run table is `reports/tasks_and_rubrics.tsv`. One carried-score sync run, `sync-rerun-gemini31pro-medium`, records the recovered score but has no final video because that API run did not produce a usable local submission.

## Secret Hygiene

The public release excludes `.env`, `.secrets/`, virtual environments, and raw native session stores that may contain account metadata or keys. Historical run folders keep the task workspaces, final submissions, run histories, agent transcript summaries, score files, and verifier-readable metadata needed to audit the benchmark results.

## Task Package Structure

Each task is released as `tasks/<task_id>/` with the same public/private split:

```text
tasks/<task_id>/
  public/
    prompt.md                    # task-specific prompt shown to the agent
    tools.md                     # tool/package reference shown to the agent
    source_metadata.json          # public metadata for the source material
    output_specs.json             # required deliverables, duration/aspect gates, format expectations
    edit_decision.schema.json     # JSON schema for submit/edit_decision.json
    materials/source.mp4          # source video given to the agent
  private/
    ground_truth.json             # hidden task ground truth consumed by verifier code
    verifier_config.json          # scoring weights, gates, thresholds, and caps
    hackability_analysis.md       # task-specific reward-hacking risks and defenses
```

Some tasks include additional private verifier files. `piecewise_av_sync_repair/private/clean_reference.mp4` and `required_spans.json` support sync/content-preservation checks. `rough_interview_caption_cleanup/private/semantic_anchors.json`, `defect_map.json`, and `public_timeline.json` support semantic preservation and caption cleanup checks. The pancake task keeps private interval/coverage criteria in `ground_truth.json` and `verifier_config.json`.
