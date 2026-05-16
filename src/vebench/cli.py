from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

from .agents.docker_runner import run_in_docker
from .config import default_image
from .fs import read_json, write_json
from .reporting.aggregate import aggregate_scores
from .runs import prepare_run
from .tasks.package import generate_task_package
from .tasks.registry import task_ids
from .tasks.roi_annotation import annotate_task_rois
from .verifiers.task_specific import score_task_submission

app = typer.Typer(help="Video editing RL mini-benchmark CLI.")
console = Console()


@app.command()
def generate(
    task: str = "all",
    out_dir: Path = Path("tasks"),
    source: Optional[Path] = typer.Option(None, "--source", help="Optional local source video to package."),
    force: bool = typer.Option(False, "--force", help="Overwrite the generated task directory."),
) -> None:
    """Generate task5/task7/task13 public/private task packages."""
    selected = task_ids() if task == "all" else [task]
    if source is not None and task == "all":
        console.print("[yellow]--source applies to one task at a time; writing metadata-only packages for all tasks.[/yellow]")
        source = None
    for task_id in selected:
        task_root = generate_task_package(task_id=task_id, out_dir=out_dir, source=source, force=force)
        public_source = task_root / "public" / "materials" / "source.mp4"
        suffix = "with source.mp4" if public_source.exists() else "metadata only; add --source to create materials/source.mp4"
        console.print(f"[green]created[/green] {task_root} ({suffix})")


@app.command()
def prepare(
    agent: str = typer.Option(..., "--agent"),
    task: str = typer.Option(..., "--task"),
    run_id: Optional[str] = None,
    repo: Path = Path("."),
    runs_dir: Path = Path("runs"),
) -> None:
    """Create a sandbox workspace for one agent/task run."""
    record = prepare_run(repo=repo, runs_dir=runs_dir, task_id=task, agent=agent, run_id=run_id)
    console.print(record.model_dump_json(indent=2))


@app.command()
def annotate_roi(
    task: str = typer.Option("expert_pancake_vertical_short", "--task"),
    repo: Path = Path("."),
    model: str = typer.Option("gpt-5.5", "--model", help="OpenAI vision-capable model for ROI annotation."),
    frames_per_step: int = typer.Option(3, "--frames-per-step", min=1, max=8),
) -> None:
    """Create private LLM/VLM ROI annotations for crop containment scoring."""
    path = annotate_task_rois(repo=repo, task_id=task, model=model, frames_per_step=frames_per_step)
    console.print(f"[green]wrote[/green] {path}")


@app.command()
def run(
    run_id: str = typer.Option(..., "--run-id"),
    agent: Optional[str] = None,
    runs_dir: Path = Path("runs"),
    image: str = default_image(),
    cpus: str = "8",
    memory: str = "16g",
    network: str = "bridge",
    model: Optional[str] = typer.Option(None, "--model", help="Optional model name for CLIs that support model selection."),
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
        model=model,
    )
    record["status"] = "completed" if rc == 0 else "failed"
    record["metadata"]["returncode"] = rc
    if model:
        record["metadata"]["model"] = model
    write_json(run_root / "run.json", record)
    raise typer.Exit(rc)


@app.command()
def verify(
    run_id: str = typer.Option(..., "--run-id"),
    runs_dir: Path = Path("runs"),
    repo: Path = Path("."),
    llm_judge: bool = typer.Option(False, "--llm-judge", help="Run GPT-5.5 LLM-as-judge if OPENAI_API_KEY is set."),
    llm_model: str = typer.Option("gpt-5.5", "--llm-model", help="OpenAI model for LLM-as-judge."),
) -> None:
    """Score one run with the task-specific verifier."""
    run_root = runs_dir / run_id
    record = read_json(run_root / "run.json")
    score = score_task_submission(
        run_id=record["run_id"],
        task_id=record["task_id"],
        agent=record["agent"],
        workspace=Path(record["workspace"]),
        repo=repo,
        llm_judge=llm_judge,
        llm_model=llm_model,
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
