"""兼容入口：暴露常用核算/规划函数，并可作为命令行脚本运行。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from clerkship.accounting import account, default_as_of, default_now
from clerkship.gaps import build_needs
from clerkship.io import load_bundle
from clerkship.pipeline import compare_drafts, run_pipeline
from clerkship.planning import plan_remediation


def main(argv: list[str] | None = None) -> int:
    from clerkship.cli import main as cli_main
    return cli_main(argv)


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "account",
    "build_needs",
    "compare_drafts",
    "default_as_of",
    "default_now",
    "load_bundle",
    "main",
    "plan_remediation",
    "run_pipeline",
]
