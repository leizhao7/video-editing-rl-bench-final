# Repo Framework

## Goal

The take-home asks for a mini-benchmark, not just a video tool demo. The repo should therefore
make three things painfully explicit:

1. What source material and prompt the agent receives.
2. What artifact the agent must produce.
3. How an independent verifier scores that artifact without trusting the agent's explanation.

The core abstraction is a self-contained task package:

```text
TaskPackage = prompt + materials + expected output contract + verifier-only ground truth + rubric
```

Every agent run receives a composed prompt:

```text
prompts/general_agent_prompt.md
+ tasks/<task_id>/public/prompt.md
+ submission contract
```

It also receives `tools.md`, generated from `prompts/tools_cpu.md`, as a read-only-style reference
inside the workspace. `tools.md` documents the workbench; it must not contain verifier thresholds,
ground truth, or answer-specific shortcuts.

## Recommended Architecture

```text
src/vebench/
  cli.py
  config.py
  media/
    ffmpeg.py
    ffprobe.py
    audio.py
    frames.py
    subtitles.py
  tasks/
    base.py
    registry.py
    silence_filler_trim/
      generate.py
      verify.py
    av_sync_repair/
      generate.py
      verify.py
    vertical_reframe/
      generate.py
      verify.py
  verifiers/
    base.py
    metrics_audio.py
    metrics_video.py
    anti_hack.py
  agents/
    base.py
    manual.py
    codex.py
    claude.py
    gemini.py
  reporting/
    aggregate.py
    latex.py
```

## Server Design

Use the server as a deterministic media worker. Keep the coding agent on a machine with reliable
network access, and call the server over SSH or a small API.

```text
controller machine:
  Codex / Claude Code / notebooks / report writing

video server:
  ffmpeg / ffprobe / Python env / task generation / verification / artifact storage
```

For the CPU-first version, avoid making local CUDA part of the critical path.

Install locally:

```text
ffmpeg
ffprobe
python >= 3.11
numpy
scipy
opencv-python-headless
moviepy
av
librosa
soundfile
pydub
scenedetect
Pillow
scikit-image
pandas
pydantic
tqdm
colour-science
noisereduce
imageio
imageio-ffmpeg
matplotlib
jsonschema
typer
rich
pyyaml
```

Model-heavy steps should be behind interfaces, so they can be switched between local models and
APIs later:

```text
transcribe(audio) -> transcript.json
describe_frames(frames) -> frame_descriptions.json
judge_visual_quality(output, rubric) -> vlm_judgment.json
```

## Data Layout on Server

```text
/data/video-agent/
  raw/                 # downloaded or uploaded source videos
  tasks/               # generated task packages
  submissions/         # agent outputs
  cache/               # frame/audio/model cache
  tmp/                 # scratch space
  outputs/             # final reports and videos
```

Do not keep full-frame PNG dumps indefinitely. Generate frame caches by shot or by sampled
timestamp, and clean them at the end of each run.

## Output Contract

Every task should require:

```text
output.mp4
edit_decision.json
run_history.md
agent_transcript.md
```

The verifier should primarily grade `output.mp4`. `edit_decision.json` is useful for debugging and
reward-hacking analysis, but it should not be trusted as proof that the edit was performed.
`run_history.md` and `agent_transcript.md` are audit artifacts: they should record observable
commands, errors, revisions, and checks, while avoiding hidden/private chain-of-thought.
For Docker-driven Codex/Claude runs, also snapshot native session files under
`_logs/native_sessions/<agent>/` before the ephemeral container exits.
The Docker runner should mount a persistent host directory such as
`~/.vebench-agent-home/<agent>/` to `/agent-home` so account logins and CLI session stores survive
between runs.

Suggested `edit_decision.json`:

```json
{
  "source_files": ["materials/source.mp4"],
  "operations": [
    {
      "type": "trim",
      "source_start": 12.3,
      "source_end": 18.9,
      "output_start": 0.0,
      "output_end": 6.6,
      "reason": "removed silence"
    }
  ],
  "tools_used": ["ffmpeg", "python"]
}
```

## Scoring Shape

Emit a vector of subscores plus a weighted total:

```json
{
  "task_id": "av_sync_repair",
  "agent": "codex",
  "scores": {
    "sync_error_ms": 0.93,
    "content_preservation": 1.0,
    "artifact_penalty": 0.88
  },
  "total": 0.94,
  "suspected_reward_hacking": false,
  "notes": []
}
```

Dense vectors are more useful than a single pass/fail for RL analysis, but every dimension must
include an anti-hack note.

## Agent Comparison

The repo should not assume all agents can be driven programmatically. Support three modes:

1. `manual`: user runs an agent externally and drops the `submit/` artifacts into a run workspace.
2. `shell`: local command template such as `codex exec ...` or `claude ...`.
3. `recorded`: re-score existing outputs and session logs.

This keeps the benchmark reproducible even if one agent's CLI is unavailable on the video server.
