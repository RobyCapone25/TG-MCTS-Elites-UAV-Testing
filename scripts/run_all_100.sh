#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

for mission in mission1 mission2 mission3; do
  echo "============================================================"
  echo "Running ${mission} with a strict 100-attempt simulator budget"
  echo "============================================================"
  TG_FORCE_NEW=1 python cli.py generate "case_studies/${mission}.yaml" 100
done
