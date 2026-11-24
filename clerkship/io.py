"""读取见习核算交换包。

只依赖标准库。CSV 中的空白数值按 ``None`` 处理，逗号分隔字段转为列表。
"""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

TABLE_FIELDS: dict[str, list[str]] = {
    "student.csv": ["id", "course", "rotation", "home", "apply_order", "deadline"],
    "obligation.csv": ["course", "scenario", "required", "simulation_allowed"],
    "travel.csv": ["origin", "destination", "minutes"],
    "busy.csv": ["student", "day", "begin", "end", "location"],
    "supervisor.csv": ["teacher", "scenario", "mode", "start_day", "end_day"],
    "opportunity.csv": [
        "id", "activity", "rotation", "day", "begin", "end", "place",
        "scenario", "mode", "teachers", "capacity",
    ],
    "announcement.csv": ["student", "opportunity", "sent_at", "status"],
    "permission.csv": [
        "activity", "restricted_mode", "allowed", "valid_from", "received_at"
    ],
    "receipt.csv": [
        "id", "student", "opportunity", "status", "received_at", "supersedes"
    ],
}

INT_FIELDS = {
    "student.csv": {"apply_order", "deadline"},
    "obligation.csv": {"required", "simulation_allowed"},
    "travel.csv": {"minutes"},
    "busy.csv": {"day", "begin", "end"},
    "supervisor.csv": {"start_day", "end_day"},
    "opportunity.csv": {"day", "begin", "end", "capacity"},
    "announcement.csv": {"sent_at"},
    "permission.csv": {"allowed", "valid_from", "received_at"},
    "receipt.csv": {"received_at"},
}

LIST_FIELDS = {"opportunity.csv": {"teachers"}}


def _value(filename: str, key: str, raw: str) -> Any:
    text = (raw or "").strip()
    if key in INT_FIELDS.get(filename, set()):
        if text == "":
            return None
        value = int(text)
        if key == "simulation_allowed":
            return bool(value)
        return value
    if key in LIST_FIELDS.get(filename, set()):
        return [part.strip() for part in text.split(",") if part.strip()]
    return text or None


def read_table(root: Path, filename: str, fields: list[str] | None = None) -> list[dict[str, Any]]:
    """读取一张表并做基础类型转换。"""
    fields = fields or TABLE_FIELDS[filename]
    path = root / filename
    with path.open(encoding="utf-8", newline="") as source:
        reader = csv.DictReader(source, strict=True)
        if reader.fieldnames != fields:
            raise ValueError(f"{filename} 的表头与资料清单不符：{reader.fieldnames!r}")
        rows: list[dict[str, Any]] = []
        for line, raw_row in enumerate(reader, start=2):
            if None in raw_row or any(key is None for key in raw_row):
                raise ValueError(f"{filename} 第 {line} 行存在多余字段")
            if set(raw_row) != set(fields):
                raise ValueError(f"{filename} 第 {line} 行字段数量不符")
            row = {key: _value(filename, key, raw_row[key]) for key in fields}
            row["_line"] = line
            rows.append(row)
        return rows


def load_bundle(root: str | Path) -> dict[str, list[dict[str, Any]]]:
    """读取完整交换包。

    若存在 manifest.json，以清单为准；否则使用内置资料口径。这样小型测试包
    即使没有 manifest 也可直接构造。
    """
    root = Path(root)
    manifest_path = root / "manifest.json"
    bundle: dict[str, list[dict[str, Any]]] = {}
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for filename, fields in manifest.items():
            bundle[Path(filename).stem] = read_table(root, filename, list(fields))
    else:
        for filename, fields in TABLE_FIELDS.items():
            if (root / filename).exists():
                bundle[Path(filename).stem] = read_table(root, filename, fields)
            else:
                bundle[Path(filename).stem] = []

    return bundle


def table(bundle: dict[str, Any], name: str) -> list[dict[str, Any]]:
    return bundle.get(name, [])
