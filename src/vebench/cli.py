from pathlib import Path

import typer
from rich.console import Console

from .agents.docker_runner import run_in_docker
from .config import default_image, ensure_dir
from .fs import read_json, write_json
from .reporting.aggregate import aggregate_scores
from .runs import prepare_run
from .verifiers.basic import basic_submission_score

app = typer.Typer(help="Video editing RL mini-benchmark CLI.")
console = Console()


@app.command()
def generate(task: str = "all", out_dir: Path = Path("tasks")) -> None:
    """Generate placeholder task package directories."""
    task_ids = ["silence_filler_trim", "av_sync_repair", "vertical_reframe"] if task == "all" else [task]
    tools_template = Path("prompts/tools_cpu.md")
    tools_text = tools_template.read_text() if tools_template.exists() else "# Available Tools\n\n- ffmpeg\n- ffprobe\n- python\n"
    for task_id in task_ids:
        public = out_dir / task_id / "public"
        private = out_dir / task_id / "private"
        ensure_dir(public / "materials")
        ensure_dir(private)
        (public / "prompt.md").write_text(
            f"# Task: {task_id}\n\n"
            "Use the provided source materials to create `submit/output.mp4` and "
            "`submit/edit_decision.json`.\n"
        )
        (public / "tools.md").write_text(tools_text.rstrip() + "\n")
        (private / "ground_truth.json").write_text("{\n  \"todo\": true\n}\n")
        (private / "rubric.yaml").write_text("todo: true\n")
        console.print(f"[green]created[/green] {public}")


@app.command()
def prepare(
    agent: str = typer.Option(..., "--agent"),
    task: str = typer.Option(..., "--task"),
    run_id: str | None = None,
    repo: Path = Path("."),
    runs_dir: Path = Path("runs"),
) -> None:
    """Create a sandbox workspace for one agent/task run."""
    record = prepare_run(repo=repo, runs_dir=runs_dir, task_id=task, agent=agent, run_id=run_id)
    console.print(record.model_dump_json(indent=2))


@app.command()
def run(
    run_id: str = typer.Option(..., "--run-id"),
    agent: str | None = None,
    runs_dir: Path = Path("runs"),
    image: str = default_image(),
    cpus: str = "8",
    memory: str = "16g",
    network: str = "bridge",
) -> None:
    """Run Codex, Claude Code, or a smoke agent inside Docker."""
    run_root = runs_dir / run_id
    record = read_json(run_root / "run.json")
    selected_agent = agent or record["agent"]
    rc = run_in_docker(
        agent=selected_agent,
        workspace=Path(record["workspace"]),
        image=image,
        cpus=cpus,
        memory=memory,
        network=network,
    )
    record["status"] = "completed" if rc == 0 else "failed"
    record["metadata"]["returncode"] = rc
    write_json(run_root / "run.json", record)
    raise typer.Exit(rc)


@app.command()
def verify(run_id: str = typer.Option(..., "--run-id"), runs_dir: Path = Path("runs")) -> None:
    """Score one run with the basic verifier placeholder."""
    run_root = runs_dir / run_id
    record = read_json(run_root / "run.json")
    score = basic_submission_score(
        run_id=record["run_id"],
        task_id=record["task_id"],
        agent=record["agent"],
        workspace=Path(record["workspace"]),
    )
    write_json(run_root / "score.json", score.model_dump(mode="json"))
    console.print(score.model_dump_json(indent=2))


@app.command()
def report(runs_dir: Path = Path("runs"), output: Path = Path("reports/tasks_and_rubrics.tsv")) -> None:
    """Aggregate verifier outputs into the deliverable TSV."""
    path = aggregate_scores(runs_dir=runs_dir, output=output)
    console.print(f"[green]wrote[/green] {path}")


@app.command()
def doctor() -> None:
    """Print the local tool availability that matters for this benchmark."""
    import shutil
    import subprocess

    for tool in ["ffmpeg", "ffprobe", "python3.11", "docker", "node", "npm"]:
        path = shutil.which(tool)
        console.print(f"{tool}: {path or '[red]missing[/red]'}")
    if shutil.which("ffmpeg"):
        subprocess.run(["ffmpeg", "-version"], check=False)


if __name__ == "__main__":
    app()
