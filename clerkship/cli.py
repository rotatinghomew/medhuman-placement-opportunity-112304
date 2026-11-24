"""命令行入口：每轮对同一交换包重跑并输出复核材料。"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .pipeline import compare_drafts, run_pipeline
from .report import query_rotation, write_draft_comparison, write_outputs


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="机会核算与补学安排工具")
    parser.add_argument("bundle", type=Path, help="含 manifest.json 和 CSV 的交换包目录")
    parser.add_argument("--out", type=Path, default=Path("out"), help="输出目录")
    parser.add_argument("--as-of", type=int, default=None, help="证据收件截止绝对分钟；默认使用全部证据")
    parser.add_argument("--now", type=int, default=None, help="协调员复核时点；默认取最晚现场回执时间")
    parser.add_argument("--consents", type=Path, default=None, help="已获学生同意的换约 JSON 文件")
    parser.add_argument("--compare-old", type=int, default=None, help="输出与指定旧证据时点草案的差异")
    parser.add_argument("--compare-new", type=int, default=None, help="对比草案的新证据时点，默认全部证据")
    parser.add_argument("--query-rotation", type=str, default=None, help="只打印指定原轮转的指标、决定和依据 JSON")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    consents = None
    if args.consents:
        consents = json.loads(args.consents.read_text(encoding="utf-8"))
    result = run_pipeline(args.bundle, as_of=args.as_of, now=args.now, consents=consents)
    draft_changes = None
    if args.compare_old is not None:
        draft_changes = compare_drafts(args.bundle, args.compare_old, args.compare_new)
        result["draft_changes"] = {
            "old_as_of": draft_changes["old_as_of"],
            "new_as_of": draft_changes["new_as_of"],
            "changes": draft_changes["changes"],
        }
    write_outputs(result, args.out)
    if draft_changes is not None:
        write_draft_comparison(args.bundle, args.compare_old, args.compare_new, args.out)
        print(json.dumps(draft_changes["changes"], ensure_ascii=False, indent=2))
    if args.query_rotation:
        print(json.dumps(query_rotation(result, args.query_rotation), ensure_ascii=False, indent=2, default=str))
    print(f"已输出复核材料到：{args.out}")
    print(f"复核时点 now={result['now']}；安排 {len(result['plan']['assignments'])} 项；"
          f"未决 {len(result['plan']['unresolved'])} 项；"
          f"换约征询 {len(result['plan']['swap_consultations'])} 项。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
