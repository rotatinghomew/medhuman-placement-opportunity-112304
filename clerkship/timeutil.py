"""时间、路程和冲突判断。"""
from __future__ import annotations

from typing import Any, Iterable

DAY = 1440


def absolute(day: int, minute: int | None = 0) -> int:
    """按资料口径把“日 × 1440 + 当天分钟”转为绝对分钟。"""
    return int(day) * DAY + int(minute or 0)


def interval(row: dict[str, Any]) -> tuple[int, int]:
    return absolute(row["day"], row["begin"]), absolute(row["day"], row["end"])


def overlaps(start_a: int, end_a: int, start_b: int, end_b: int) -> bool:
    """区间左闭右开。"""
    return max(start_a, start_b) < min(end_a, end_b)


def travel_minutes(
    travel: list[dict[str, Any]], origin: str | None, destination: str | None
) -> int | None:
    if not origin or not destination:
        return None
    for row in travel:
        if row["origin"] == origin and row["destination"] == destination:
            return row["minutes"]
    return None


def arrival_check(
    student: dict[str, Any],
    opportunity: dict[str, Any],
    busy: list[dict[str, Any]],
    travel: list[dict[str, Any]],
    *,
    sent_at: int | None = None,
    extra_blocks: Iterable[dict[str, Any]] = (),
) -> dict[str, Any]:
    """判断学生按已公布课表和受保护预约能否按时到达。

    返回结构化依据，而不是单个布尔值；调用方可同时保留“已通知”等不同事实。
    """
    opp_start, opp_end = interval(opportunity)
    day = int(opportunity["day"])
    blocks: list[dict[str, Any]] = []

    for row in busy:
        if row["student"] != student["id"] or int(row["day"]) != day:
            continue
        start, end = interval(row)
        blocks.append({
            "kind": "busy",
            "ref": f"busy:L{row.get('_line', '?')}",
            "start": start,
            "end": end,
            "location": row.get("location"),
        })

    for row in extra_blocks:
        if int(row.get("day", -1)) != day:
            continue
        start = int(row["start_abs"])
        end = int(row["end_abs"])
        blocks.append({
            "kind": row.get("kind", "accepted"),
            "ref": row.get("ref", "accepted"),
            "start": start,
            "end": end,
            "location": row.get("location", opportunity.get("place")),
        })

    conflicts = [b for b in blocks if overlaps(opp_start, opp_end, b["start"], b["end"])]
    if conflicts:
        return {
            "feasible": False,
            "reason": "schedule_conflict",
            "source": "student",
            "conflicts": conflicts,
            "earliest_arrival": None,
            "travel_minutes": None,
            "origin": None,
        }

    previous = [b for b in blocks if b["end"] <= opp_start]
    if previous:
        latest = max(previous, key=lambda b: (b["end"], b["start"]))
        origin = latest.get("location") or student.get("home")
        free_at = latest["end"]
        block_ref = latest["ref"]
    else:
        origin = student.get("home")
        free_at = None
        block_ref = None

    minutes = travel_minutes(travel, origin, opportunity.get("place"))
    if minutes is None:
        return {
            "feasible": False,
            "reason": "travel_unknown",
            "source": "undetermined",
            "conflicts": [],
            "earliest_arrival": None,
            "travel_minutes": None,
            "origin": origin,
            "block_ref": block_ref,
        }

    # 未通知时不允许“提前知道”而出发；已通知很久时，通知时间不会额外阻碍。
    ready_at = free_at
    if sent_at is not None:
        ready_at = sent_at if ready_at is None else max(ready_at, sent_at)
    if ready_at is None:
        # 没有更早的课表/通知约束：学生可在开课前按路程从家出发。
        earliest = opp_start - minutes
        feasible = True
    else:
        earliest = ready_at + minutes
        feasible = earliest <= opp_start

    if not feasible:
        reason = "notice_too_late" if sent_at is not None and free_at is None and sent_at + minutes > opp_start else "travel_impossible"
        return {
            "feasible": False,
            "reason": reason,
            "source": "student",
            "conflicts": [],
            "earliest_arrival": earliest,
            "travel_minutes": minutes,
            "origin": origin,
            "block_ref": block_ref,
        }

    return {
        "feasible": True,
        "reason": "arrival_feasible",
        "source": None,
        "conflicts": [],
        "earliest_arrival": earliest if ready_at is not None else opp_start - minutes,
        "travel_minutes": minutes,
        "origin": origin,
        "block_ref": block_ref,
    }
