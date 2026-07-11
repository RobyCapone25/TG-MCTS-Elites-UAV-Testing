#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

if [[ -f "$HOME/miniconda3/etc/profile.d/conda.sh" ]]; then
  # shellcheck disable=SC1091
  source "$HOME/miniconda3/etc/profile.d/conda.sh"
elif [[ -f "$HOME/anaconda3/etc/profile.d/conda.sh" ]]; then
  # shellcheck disable=SC1091
  source "$HOME/anaconda3/etc/profile.d/conda.sh"
fi

if command -v conda >/dev/null 2>&1; then
  conda activate uav
fi

cd "$PROJECT_ROOT"

./scripts/run_harmonized.sh generate case_studies/mission1.yaml 100 --fresh
./scripts/run_harmonized.sh generate case_studies/mission2.yaml 100 --fresh
./scripts/run_harmonized.sh generate case_studies/mission3.yaml 100 --fresh

echo "All 3 harmonized mission runs finished."
