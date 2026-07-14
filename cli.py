#!/usr/bin/env python3
"""Root launcher preserving the competition command-line interface."""

from pathlib import Path
import runpy
import sys

PROJECT_ROOT = Path(__file__).resolve().parent
SRC_DIR = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_DIR))
runpy.run_path(str(SRC_DIR / "cli.py"), run_name="__main__")
