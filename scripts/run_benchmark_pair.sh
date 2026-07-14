#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

MISSION="${1:-mission1}"
BUDGET="${2:-100}"
SEED="${3:-12345}"
CASE_STUDY="case_studies/${MISSION}.yaml"

if [[ ! -f "$CASE_STUDY" ]]; then
  echo "Missing case study: $CASE_STUDY" >&2
  exit 1
fi
if ! [[ "$BUDGET" =~ ^[1-9][0-9]*$ ]]; then
  echo "Budget must be a positive integer: $BUDGET" >&2
  exit 1
fi
if ! [[ "$SEED" =~ ^[0-9]+$ ]]; then
  echo "Seed must be a non-negative integer: $SEED" >&2
  exit 1
fi

run_algorithm() {
  local algorithm="$1"
  local namespace="$2"
  local algorithm_id="$3"
  local action

  action="$(
    python tools/benchmark_status.py \
      --results-dir results \
      --namespace "$namespace" \
      --algorithm-id "$algorithm_id" \
      --case-study "$CASE_STUDY" \
      --seed "$SEED" \
      --budget "$BUDGET" \
      --prepare
  )"

  echo "============================================================"
  echo "Algorithm: ${algorithm}"
  echo "Mission:   ${MISSION}"
  echo "Budget:    ${BUDGET} simulator attempts"
  echo "Seed:      ${SEED}"
  echo "Action:    ${action}"
  echo "============================================================"

  if [[ "$action" == "completed" ]]; then
    echo "Exact completed run already exists; skipping it."
    return 0
  fi

  TG_SEED="$SEED" \
  TG_RESUME_STRICT_BUDGET=1 \
  PYTHONPATH="$ROOT_DIR/src${PYTHONPATH:+:$PYTHONPATH}" \
    python cli.py generate "$CASE_STUDY" "$BUDGET" --algorithm "$algorithm"

  action="$(
    python tools/benchmark_status.py \
      --results-dir results \
      --namespace "$namespace" \
      --algorithm-id "$algorithm_id" \
      --case-study "$CASE_STUDY" \
      --seed "$SEED" \
      --budget "$BUDGET"
  )"
  if [[ "$action" != "completed" ]]; then
    echo "Run did not reach a finalized completed state: ${algorithm}" >&2
    exit 1
  fi
}

run_algorithm "tg-mcts-elites" "tg_mcts_elites" "tg_mcts_elites"
run_algorithm "random-search" "random_search" "operator_random_search"
