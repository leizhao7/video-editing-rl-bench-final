# VPS Runbook

Repo path on the VPS:

```bash
cd /bench/video-editing-rl-bench
source .venv/bin/activate
```

Storage:

```text
/data/video-agent/        large data disk
/data/video-agent/docker  Docker data-root
/bench/video-editing-rl-bench  benchmark repo
```

Check the environment:

```bash
vebench doctor
docker run --rm video-bench-agent:cpu bash -lc 'python --version; command -v codex; command -v claude; ffmpeg -version | head -1'
```

Generate task package skeletons:

```bash
vebench generate --task all
```

Each prepared run composes:

```text
prompts/general_agent_prompt.md
+ tasks/<task_id>/public/prompt.md
+ submission contract
```

and copies the CPU tool reference into `runs/<run_id>/workspace/tools.md`.

Prepare one sandbox workspace:

```bash
vebench prepare --agent codex --task silence_filler_trim --run-id codex-silence-001
```

Run a smoke agent without API keys:

```bash
vebench run --run-id smoke1 --agent shell-smoke --cpus 2 --memory 2g
vebench verify --run-id smoke1
vebench report
```

Run Codex:

```bash
export OPENAI_API_KEY=...
vebench prepare --agent codex --task silence_filler_trim --run-id codex-silence-001
vebench run --run-id codex-silence-001 --agent codex --cpus 8 --memory 16g
vebench verify --run-id codex-silence-001
```

Run Claude Code:

```bash
export ANTHROPIC_API_KEY=...
vebench prepare --agent claude --task silence_filler_trim --run-id claude-silence-001
vebench run --run-id claude-silence-001 --agent claude --cpus 8 --memory 16g
vebench verify --run-id claude-silence-001
```

Sandbox boundary:

```text
Container sees:
  runs/<run_id>/workspace

Container does not see:
  tasks/<task_id>/private
  verifier source as a mounted host path
  Docker socket
```

Do not mount `/var/run/docker.sock` into agent containers.
