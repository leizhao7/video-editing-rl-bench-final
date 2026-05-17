#!/usr/bin/env bash
set -euo pipefail

MATRIX_FILE="${MATRIX_FILE:-configs/final_model_matrix.tsv}"
RUNS_DIR="${RUNS_DIR:-runs}"
REPORT_PATH="${REPORT_PATH:-reports/tasks_and_rubrics.tsv}"
IMAGE="${IMAGE:-video-bench-agent:cpu}"
PYTHON_BIN="${PYTHON_BIN:-}"
TASK_FILTER="${TASK_FILTER:-}"
AGENT_FILTER="${AGENT_FILTER:-}"
VEBENCH_LLM_JUDGE="${VEBENCH_LLM_JUDGE:-1}"
VEBENCH_LLM_JUDGE_MODEL="${VEBENCH_LLM_JUDGE_MODEL:-gpt-5.5}"

if [[ -z "${PYTHON_BIN}" ]]; then
  if [[ -x ".venv/bin/python" ]]; then
    PYTHON_BIN=".venv/bin/python"
  else
    PYTHON_BIN="python3"
  fi
fi

if [[ ! -f "${MATRIX_FILE}" ]]; then
  echo "Missing matrix file: ${MATRIX_FILE}" >&2
  exit 2
fi

while IFS=$'\t' read -r task_id agent model effort run_id; do
  [[ -z "${task_id:-}" || "${task_id:0:1}" == "#" ]] && continue
  if [[ -n "${TASK_FILTER}" && "${TASK_FILTER}" != "${task_id}" ]]; then
    continue
  fi
  if [[ -n "${AGENT_FILTER}" && "${AGENT_FILTER}" != "${agent}" ]]; then
    continue
  fi

  echo "==> ${run_id}: ${task_id} / ${agent} / ${model} / ${effort}"
  "${PYTHON_BIN}" -m vebench.cli prepare \
    --agent "${agent}" \
    --task "${task_id}" \
    --run-id "${run_id}" \
    --runs-dir "${RUNS_DIR}"

  "${PYTHON_BIN}" -m vebench.cli run \
    --run-id "${run_id}" \
    --runs-dir "${RUNS_DIR}" \
    --image "${IMAGE}" \
    --model "${model}" \
    --effort "${effort}"

  verify_args=(
    -m vebench.cli verify
    --run-id "${run_id}"
    --runs-dir "${RUNS_DIR}"
  )
  if [[ "${VEBENCH_LLM_JUDGE}" == "1" ]]; then
    verify_args+=(--llm-judge --llm-model "${VEBENCH_LLM_JUDGE_MODEL}")
  fi
  "${PYTHON_BIN}" "${verify_args[@]}"
done < "${MATRIX_FILE}"

"${PYTHON_BIN}" -m vebench.cli report \
  --runs-dir "${RUNS_DIR}" \
  --output "${REPORT_PATH}"

echo "Final report written to ${REPORT_PATH}"
