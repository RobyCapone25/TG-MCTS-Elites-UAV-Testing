#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
mkdir -p logs

set -o pipefail
TG_FORCE_NEW=1 \
PYTHONPATH="$ROOT_DIR/src" \
python cli.py generate case_studies/mission1.yaml 50 \
2>&1 | tee "logs/mission1_50_$(date +%Y-%m-%d_%H-%M-%S).log"
