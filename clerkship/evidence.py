"""回执、许可和带教资格的时点化判断。"""
from __future__ import annotations

from typing import Any

from .timeutil import absolute


def effective_receipts(receipts: list[dict[str, Any]], as_of: int | None = None) -> dict[tuple[str, str], dict[str, Any]]:
    """返回截至 as_of 仍有效的学生-机会回执。

    as_of=None 时使用交换包中的全部证据。被可见新回执显式 supersedes 的旧回执
    不再作为当前草案依据。若同一对键仍有多张未替代回执，保留冲突 ID。
    """
    if as_of is None:
        visible = list(receipts)
    else:
        visible = [r for r in receipts if (r.get("received_at") is not None and r["received_at"] <= as_of)]
    superseded_ids = {r.get("supersedes") for r in visible if r.get("supersedes")}
    current = [r for r in visible if r["id"] not in superseded_ids]

    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in current:
        grouped.setdefault((row["student"], row["opportunity"]), []).append(row)

    result: dict[tuple[str, str], dict[str, Any]] = {}
    for key, rows in grouped.items():
        rows = sorted(rows, key=lambda r: (r["received_at"], r["id"]))
        if len(rows) == 1:
            result[key] = {**rows[0], "conflict_ids": []}
        else:
            statuses = {r["status"] for r in rows}
            latest = rows[-1]
            result[key] = {
                **latest,
                "conflict_ids": [r["id"] for r in rows[:-1]],
                "conflicting_statuses": sorted(statuses),
            }
    return result


def visible_announcements(announcements: list[dict[str, Any]], as_of: int | None = None) -> list[dict[str, Any]]:
    if as_of is None:
        return list(announcements)
    return [a for a in announcements if a.get("sent_at") is not None and a["sent_at"] <= as_of]


def supervision_ok(opp: dict[str, Any], supervisors: list[dict[str, Any]]) -> dict[str, Any]:
    teachers = opp.get("teachers") or []
    matching = [
        s for s in supervisors
        if s.get("teacher") in teachers
        and s.get("scenario") == opp["scenario"]
        and s.get("mode") == opp["mode"]
        and s.get("start_day") is not None and s.get("end_day") is not None
        and s["start_day"] <= opp["day"] <= s["end_day"]
    ]
    if not teachers:
        return {"ok": False, "reason": "teacher_missing", "qualified": []}
    if matching:
        return {"ok": True, "reason": "supervision_qualified", "qualified": [s["teacher"] for s in matching]}
    return {"ok": False, "reason": "supervision_shortage", "qualified": []}


def permission_at_start(
    permissions: list[dict[str, Any]], opp: dict[str, Any], as_of: int | None = None
) -> dict[str, Any]:
    """返回该机会登记方式在开始时实际适用的许可。

    as_of 给定时，只使用教务截至该时点已收到的许可记录；但记录可以用
    valid_from 追溯见习开始前的状态变化，供新证据到达后重算。
    """
    start = absolute(opp["day"], opp["begin"])
    rows = [
        p for p in permissions
        if p.get("activity") == opp["activity"]
        and p.get("restricted_mode") == opp["mode"]
        and (as_of is None or (p.get("received_at") is not None and p["received_at"] <= as_of))
    ]
    if not rows:
        if opp["mode"] == "sim":
            return {
                "status": "sim_no_clinical_permission_required",
                "allowed": None,
                "row": None,
                "known_rows": [],
                "source": "permission",
            }
        return {
            "status": "permission_unknown",
            "allowed": None,
            "row": None,
            "known_rows": [],
            "source": "undetermined",
        }

    applicable = [p for p in rows if p.get("valid_from") is not None and p["valid_from"] <= start]
    if not applicable:
        return {
            "status": "permission_not_effective_at_start",
            "allowed": None,
            "row": None,
            "known_rows": [p["id"] if "id" in p else f"L{p.get('_line')}" for p in rows],
            "source": "undetermined",
        }
    row = max(applicable, key=lambda p: (p["valid_from"], p.get("received_at") or 0, p.get("_line") or 0))
    if row["allowed"] == 0:
        status = "permission_denied"
        source = "activity"
    else:
        status = "permission_ok"
        source = None
    return {"status": status, "allowed": row["allowed"], "row": row, "source": source}


def original_permission(permissions: list[dict[str, Any]], opp: dict[str, Any]) -> dict[str, Any]:
    """最早登记口径，用于展示原计划和实际口径的差异。"""
    rows = [
        p for p in permissions
        if p.get("activity") == opp["activity"] and p.get("restricted_mode") == opp["mode"]
    ]
    if not rows:
        return {"allowed": None, "status": "not_registered"}
    row = min(rows, key=lambda p: (p.get("valid_from") or 0, p.get("_line") or 0))
    return {"allowed": row["allowed"], "status": "original_registered", "row": row}
