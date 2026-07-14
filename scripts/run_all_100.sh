#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

mkdir -p logs

for mission in mission1 mission2 mission3; do
    STAMP="$(date +%Y-%m-%d_%H-%M-%S)"
    LOG_FILE="logs/${mission}_100_${STAMP}.log"

    echo "============================================================"
    echo "${mission}: fresh run"
    echo "Strict simulator-attempt budget: 100"
    echo "Transcript: $LOG_FILE"
    echo "============================================================"

    TG_FORCE_NEW=1 \
    PYTHONPATH="$ROOT_DIR/src" \
    MPLBACKEND=Agg \
    python cli.py generate "case_studies/${mission}.yaml" 100 \
    2>&1 | tee "$LOG_FILE"
done
