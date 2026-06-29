#!/bin/bash

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

source ~/miniconda3/etc/profile.d/conda.sh 2>/dev/null || source ~/anaconda3/etc/profile.d/conda.sh
conda activate uav

cd "$PROJECT_ROOT"

mkdir -p results/batch_logs

echo "Starting 100 simulations for mission1 with fresh run..."
TG_FORCE_NEW=1 python cli.py generate case_studies/mission1.yaml 100 2>&1 | tee results/batch_logs/mission1_100.log

echo "Starting 100 simulations for mission2 with fresh run..."
TG_FORCE_NEW=1 python cli.py generate case_studies/mission2.yaml 100 2>&1 | tee results/batch_logs/mission2_100.log

echo "Starting 100 simulations for mission3 with fresh run..."
TG_FORCE_NEW=1 python cli.py generate case_studies/mission3.yaml 100 2>&1 | tee results/batch_logs/mission3_100.log

echo "All 3 missions finished."
