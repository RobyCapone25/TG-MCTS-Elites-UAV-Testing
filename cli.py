#!/usr/bin/env python3
"""
Root launcher for the UAV test generator.

The real CLI implementation is in src/cli.py.
This wrapper keeps the original command working:

    python cli.py generate case_studies/mission1.yaml 10
"""

from pathlib import Path
import runpy
import sys

PROJECT_ROOT = Path(__file__).resolve().parent
SRC_DIR = PROJECT_ROOT / "src"

sys.path.insert(0, str(SRC_DIR))

runpy.run_path(str(SRC_DIR / "cli.py"), run_name="__main__")
