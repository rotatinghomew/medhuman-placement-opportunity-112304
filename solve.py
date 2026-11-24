#!/usr/bin/env python3
"""免安装入口：python3 -I /workspace/solve.py /workspace/data --out /workspace/out"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from clerkship.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
