#!/usr/bin/env bash
set -euo pipefail

TASK_ID="${TASK_ID:-piecewise_av_sync_repair}"
AGENT="${AGENT:-shell-smoke}"
RUN_ID="${RUN_ID:-demo-${TASK_ID}-${AGENT}}"
IMAGE="${IMAGE:-video-bench-agent:cpu}"
RUNS_DIR="${RUNS_DIR:-runs}"
REPORT_PATH="${REPORT_PATH:-reports/tasks_and_rubrics.tsv}"
PYTHON_BIN="${PYTHON_BIN:-}"

if [[ -z "${PYTHON_BIN}" ]]; then
  if [[ -x ".venv/bin/python" ]]; then
    PYTHON_BIN=".venv/bin/python"
  else
    PYTHON_BIN="python3"
  fi
fi

"${PYTHON_BIN}" -m vebench.cli prepare \
  --agent "${AGENT}" \
  --task "${TASK_ID}" \
  --run-id "${RUN_ID}" \
  --runs-dir "${RUNS_DIR}"

"${PYTHON_BIN}" -m vebench.cli run \
  --run-id "${RUN_ID}" \
  --runs-dir "${RUNS_DIR}" \
  --image "${IMAGE}"

"${PYTHON_BIN}" -m vebench.cli verify \
  --run-id "${RUN_ID}" \
  --runs-dir "${RUNS_DIR}"

"${PYTHON_BIN}" -m vebench.cli report \
  --runs-dir "${RUNS_DIR}" \
  --output "${REPORT_PATH}"

echo "Demo complete: ${RUN_ID}"
echo "Report written to: ${REPORT_PATH}"
