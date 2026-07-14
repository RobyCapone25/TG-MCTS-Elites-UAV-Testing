#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

MISSION="${1:-mission1}"
BUDGET="${2:-50}"
SEED_ONE="${3:-1001}"
SEED_TWO="${4:-1002}"

if [[ "$SEED_ONE" == "$SEED_TWO" ]]; then
  echo "The two paired seeds must be different." >&2
  exit 1
fi

for seed in "$SEED_ONE" "$SEED_TWO"; do
  ./scripts/run_benchmark_pair.sh "$MISSION" "$BUDGET" "$seed"
done

python tools/aggregate_benchmarks.py

echo "============================================================"
echo "Two-seed benchmark complete"
echo "Mission: ${MISSION}"
echo "Budget:  ${BUDGET}"
echo "Seeds:   ${SEED_ONE}, ${SEED_TWO}"
echo "Plots:   results/benchmark_comparison/plots/"
echo "============================================================"
