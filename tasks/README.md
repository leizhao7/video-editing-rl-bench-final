# Task Proposal Workspace

This folder is for task-design proposals created by worker agents.

Each worker gets an isolated subfolder:

```text
tasks/worker_01/
tasks/worker_02/
...
tasks/worker_10/
```

Each worker must write exactly one Markdown report inside its own folder:

```text
tasks/worker_<id>/report.md
```

Example:

```text
tasks/worker_03/report.md
```

The Markdown file must follow `TASK_PROPOSAL_TEMPLATE.md`. Workers should not read, summarize,
compare against, or modify any sibling `tasks/worker_*` directory. Each worker should work
independently from the shared prompt, template, and available tool list only.

Do not commit downloaded YouTube videos, derived media, temporary frames, model outputs, or
large artifacts into this folder. The proposal should contain YouTube URLs, clip time ranges,
metadata, task design, verifier design, reward dimensions, and anti-hacking analysis.
