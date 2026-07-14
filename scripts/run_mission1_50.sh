#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

mkdir -p logs
STAMP="$(date +%Y-%m-%d_%H-%M-%S)"
LOG_FILE="logs/mission1_50_${STAMP}.log"

echo "============================================================"
echo "Mission 1: fresh run"
echo "Strict simulator-attempt budget: 50"
echo "Transcript: $LOG_FILE"
echo "============================================================"

TG_FORCE_NEW=1 \
PYTHONPATH="$ROOT_DIR/src" \
MPLBACKEND=Agg \
python cli.py generate case_studies/mission1.yaml 50 \
2>&1 | tee "$LOG_FILE"
