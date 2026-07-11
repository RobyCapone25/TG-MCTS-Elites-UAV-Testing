#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 2 ]]; then
  echo "Usage: ./scripts/run_harmonized.sh case_studies/mission1.yaml BUDGET [--fresh]"
  exit 2
fi

mission="$1"
budget="$2"
mode="${3:-}"

if [[ "$mode" == "--fresh" ]]; then
  TG_FORCE_NEW=1 python cli.py generate "$mission" "$budget"
elif [[ -z "$mode" ]]; then
  python cli.py generate "$mission" "$budget"
else
  echo "ERROR: unknown option: $mode"
  exit 2
fi
