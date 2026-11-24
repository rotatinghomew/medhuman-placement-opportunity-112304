"""机会核算：原计划、当天实际可参加、实际完成三种口径。"""
from __future__ import annotations

from collections import defaultdict
from typing import Any

from .evidence import (
    effective_receipts,
    original_permission,
    permission_at_start,
    supervision_ok,
    visible_announcements,
)
from .timeutil import absolute, interval, overlaps, arrival_check

PAST_GRACE = 0

SOURCE_LABELS = {
    "supervision": "带教不足",
    "activity": "教学活动未发生（取消、同意撤回、许可或容量变化）",
    "student": "学生不能到场（时间/路程冲突或已确认缺席）",
    "undetermined": "资料无法确定",
    "pending": "预约尚未到期",
    "none": "无损失",
}

REASON_LABELS = {
    "completed": "学生已到场完成",
    "available": "机会可用",
    "not_due": "尚未到回执时间",
    "student_confirmed_absent": "现场回执已确认未到；不得按院方损失补偿",
    "activity_cancelled": "回执确认机会取消/教学活动未发生",
    "receipt_cancelled": "回执确认机会取消/教学活动未发生",
    "consent_withdrawn": "同意撤回或家属临时谢绝旁听",
    "receipt_refused": "同意撤回或家属临时谢绝旁听",
    "permission_denied": "许可明确允许0人观察",
    "permission_unknown": "缺少对应观察方式的许可，资料无法确定",
    "permission_not_effective_at_start": "开始时没有已生效许可",
    "supervision_shortage": "所列教师没有覆盖该场景/方式/日期的带教资格",
    "teacher_missing": "未登记带教教师",
    "schedule_conflict": "与已有课业或受保护预约时间冲突",
    "travel_impossible": "按最短路程无法按时到达",
    "notice_too_late": "通知发出时间晚于最晚出发时间",
    "travel_unknown": "缺少两地路程资料，无法判断可达性",
    "final_receipt_missing": "已过时段但没有最终回执，不能记为缺席",
    "held_appointment_without_final_receipt": "只有已接受/held记录，尚无最终现场回执",
    "physical_capacity_filled_by_present_student": "实地容量已被到场学生占满，另一名学生失去机会",
    "permission_capacity_filled_by_present_student": "许可人数已被到场学生占满，另一名学生失去机会",
}


def default_as_of(bundle: dict[str, list[dict[str, Any]]]) -> int:
    """资料包中最后一个证据/行政时间；主要用于草案对比。"""
    values: list[int] = []
    for name in ("receipt", "permission", "announcement"):
        for row in bundle.get(name, []):
            for key in ("received_at", "sent_at"):
                value = row.get(key)
                if value is not None:
                    values.append(int(value))
    return max(values) if values else 10**12


def default_now(bundle: dict[str, list[dict[str, Any]]]) -> int:
    """协调员复核时点：默认取最晚现场回执，避免把尚未发生的预约误判为缺席。"""
    values = [int(r["received_at"]) for r in bundle.get("receipt", []) if r.get("received_at") is not None]
    if values:
        return max(values)
    values = [int(a["sent_at"]) for a in bundle.get("announcement", []) if a.get("sent_at") is not None]
    return max(values) if values else 0


def _index(rows: list[dict[str, Any]], key: str) -> dict[Any, dict[str, Any]]:
    return {row[key]: row for row in rows}


def evaluate_opportunities(
    bundle: dict[str, Any], evidence_as_of: int | None = None, now: int | None = None
) -> dict[str, dict[str, Any]]:
    students = bundle.get("student", [])
    opps = bundle.get("opportunity", [])
    supervisors = bundle.get("supervisor", [])
    permissions = bundle.get("permission", [])
    announcements = visible_announcements(bundle.get("announcement", []), evidence_as_of)
    receipts = effective_receipts(bundle.get("receipt", []), evidence_as_of)
    now = default_now(bundle) if now is None else now

    views: dict[str, dict[str, Any]] = {}
    for opp in opps:
        sup = supervision_ok(opp, supervisors)
        perm = permission_at_start(permissions, opp, evidence_as_of)
        original = original_permission(permissions, opp)
        start, end = interval(opp)

        active_signups: set[str] = set()
        protected_signups: set[str] = set()
        final_present: set[str] = set()
        final_absent: set[str] = set()
        for ann in announcements:
            if ann["opportunity"] != opp["id"]:
                continue
            receipt = receipts.get((ann["student"], opp["id"]))
            status = receipt["status"] if receipt else None
            if status in {"cancelled", "refused"}:
                continue
            active_signups.add(ann["student"])
            ann_status = ann.get("status")
            if ann_status == "accepted" or status == "held":
                protected_signups.add(ann["student"])
            if status == "present":
                final_present.add(ann["student"])
            if status == "no_show":
                final_absent.add(ann["student"])

        capacity = int(opp["capacity"] or 0)
        active = len(active_signups)
        protected = len(protected_signups)
        own_remaining = max(0, capacity - active)
        remaining = own_remaining

        if end <= now:
            time_state = "past"
        elif start <= now < end:
            time_state = "ongoing"
        else:
            time_state = "upcoming"

        bookable = (
            time_state == "upcoming"
            and sup["ok"]
            and perm["status"] in {"permission_ok", "sim_no_clinical_permission_required"}
            and remaining > 0
        )
        not_bookable_reasons = []
        if time_state != "upcoming":
            not_bookable_reasons.append(f"time_{time_state}")
        if not sup["ok"]:
            not_bookable_reasons.append(sup["reason"])
        if perm["status"] not in {"permission_ok", "sim_no_clinical_permission_required"}:
            not_bookable_reasons.append(perm["status"])
        if remaining <= 0 and time_state == "upcoming":
            not_bookable_reasons.append("capacity_exhausted")

        views[opp["id"]] = {
            "opportunity": opp,
            "supervision": sup,
            "permission": perm,
            "original_permission": original,
            "start_abs": start,
            "end_abs": end,
            "time_state": time_state,
            "active_students": sorted(active_signups),
            "protected_students": sorted(protected_signups),
            "present_students": sorted(final_present),
            "absent_students": sorted(final_absent),
            "active_count": active,
            "protected_count": protected,
            "own_remaining_capacity": own_remaining,
            "remaining_capacity": remaining,
            "bookable": bookable,
            "not_bookable_reasons": not_bookable_reasons,
        }
    # 许可按 activity+mode 覆盖总人数；同一临床事件拆出的多个机会行共享该上限。
    perm_union: dict[tuple[str, str], set[str]] = {}
    for view in views.values():
        opp = view["opportunity"]
        key = (opp["activity"], opp["mode"])
        perm_union.setdefault(key, set()).update(view["active_students"])

    for view in views.values():
        opp = view["opportunity"]
        key = (opp["activity"], opp["mode"])
        allowed = view["permission"].get("allowed")
        if allowed is not None:
            used = len(perm_union.get(key, set()))
            global_remaining = max(0, int(allowed) - used)
            view["permission_used_global"] = used
            view["permission_remaining_global"] = global_remaining
            view["remaining_capacity"] = min(view["own_remaining_capacity"], global_remaining)
            if global_remaining <= 0 and view["time_state"] == "upcoming":
                if "permission_capacity_exhausted" not in view["not_bookable_reasons"]:
                    view["not_bookable_reasons"].append("permission_capacity_exhausted")
        else:
            view["permission_used_global"] = None
            view["permission_remaining_global"] = None

        # 重新计算 bookable，使全局许可上限参与判断。
        view["bookable"] = (
            view["time_state"] == "upcoming"
            and view["supervision"]["ok"]
            and view["permission"]["status"] in {"permission_ok", "sim_no_clinical_permission_required"}
            and view["remaining_capacity"] > 0
        )

    return views


def account(bundle: dict[str, Any], as_of: int | None = None, *, now: int | None = None) -> dict[str, Any]:
    evidence_as_of = as_of
    if now is None:
        now = as_of if as_of is not None else default_now(bundle)
    students = _index(bundle.get("student", []), "id")
    opps = _index(bundle.get("opportunity", []), "id")
    busy = bundle.get("busy", [])
    travel = bundle.get("travel", [])
    announcements = visible_announcements(bundle.get("announcement", []), evidence_as_of)
    receipts = effective_receipts(bundle.get("receipt", []), evidence_as_of)
    opp_views = evaluate_opportunities(bundle, evidence_as_of=evidence_as_of, now=now)

    records: list[dict[str, Any]] = []
    for ann in announcements:
        sid = ann["student"]
        oid = ann["opportunity"]
        student = students.get(sid)
        opp = opps.get(oid)
        if student is None or opp is None:
            records.append({
                "student": sid,
                "opportunity": oid,
                "data_error": "unknown_reference",
                "loss_source": "undetermined",
                "loss_reason": "unknown_reference",
                "planned_attendable": None,
                "actual_attendable": None,
                "completed": False,
            })
            continue

        receipt = receipts.get((sid, oid))
        view = opp_views[oid]
        start, end = view["start_abs"], view["end_abs"]

        # 已接受的其他同轮预约作为冲突块；当前机会自身不阻挡自己。
        extra_blocks: list[dict[str, Any]] = []
        for other_ann in announcements:
            if other_ann["student"] != sid or other_ann["opportunity"] == oid:
                continue
            other_receipt = receipts.get((sid, other_ann["opportunity"]))
            accepted = other_ann.get("status") == "accepted" or (other_receipt and other_receipt["status"] == "held")
            if not accepted:
                continue
            other = opps[other_ann["opportunity"]]
            os_, oe_ = interval(other)
            extra_blocks.append({
                "day": other["day"], "start_abs": os_, "end_abs": oe_,
                "location": other.get("place"), "ref": other_ann["opportunity"],
                "kind": "accepted_appointment",
            })

        arrival = arrival_check(student, opp, busy, travel, sent_at=ann.get("sent_at"), extra_blocks=extra_blocks)
        sup = view["supervision"]
        perm = view["permission"]
        rstatus = receipt["status"] if receipt else None

        factors: list[dict[str, str]] = []
        if not arrival["feasible"]:
            factors.append({"source": arrival["source"], "reason": arrival["reason"]})
        if not sup["ok"]:
            factors.append({"source": "supervision", "reason": sup["reason"]})
        if perm["status"] not in {"permission_ok", "sim_no_clinical_permission_required"}:
            factors.append({"source": "undetermined" if perm["source"] == "undetermined" else "activity",
                            "reason": perm["status"]})

        completed = rstatus == "present"
        if rstatus in {"cancelled", "refused"}:
            factors.insert(0, {"source": "activity", "reason": f"receipt_{rstatus}"})
        if rstatus == "no_show":
            factors.insert(0, {"source": "student", "reason": "student_confirmed_absent"})
        if receipt and receipt.get("conflict_ids"):
            factors.append({"source": "undetermined", "reason": "conflicting_receipts"})

        # 主归因：最终回执事实优先，其次硬性供给缺陷，再学生时间，最后缺回执。
        if completed:
            primary_source = "none"
            primary_reason = "completed"
            if not arrival["feasible"] or not sup["ok"]:
                factors.append({"source": "undetermined", "reason": "present_but_precondition_conflict"})
        elif rstatus == "no_show":
            primary_source = "student"
            primary_reason = "student_confirmed_absent"
        elif rstatus == "cancelled":
            primary_source = "activity"
            primary_reason = "activity_cancelled"
        elif rstatus == "refused":
            primary_source = "activity"
            primary_reason = "consent_withdrawn"
        elif not sup["ok"]:
            primary_source = "supervision"
            primary_reason = sup["reason"]
        elif perm["status"] == "permission_denied":
            primary_source = "activity"
            primary_reason = "permission_denied"
        elif perm["source"] == "undetermined":
            primary_source = "undetermined"
            primary_reason = perm["status"]
        elif not arrival["feasible"]:
            primary_source = arrival["source"]
            primary_reason = arrival["reason"]
        elif rstatus == "held" and view["time_state"] == "past":
            primary_source = "undetermined"
            primary_reason = "held_appointment_without_final_receipt"
        elif view["time_state"] == "past" and receipt is None:
            primary_source = "undetermined"
            primary_reason = "final_receipt_missing"
        elif view["time_state"] == "upcoming":
            primary_source = "pending"
            primary_reason = "not_due"
        else:
            primary_source = "none"
            primary_reason = "available"

        # 原计划可参加：通知已构成预约，且按学生已有课表、路程和其他受保护预约
        # 能按时到达。带教/许可/现场变化放在“当天实际可用”中核算并归因。
        planned_attendable = bool(ann) and arrival["feasible"]

        if completed:
            actual_attendable: bool | None = True
        elif rstatus == "no_show":
            # 已确认未到不等于机会不存在；若有供给冲突则在 factors 暴露。
            actual_attendable = sup["ok"] and perm["status"] in {
                "permission_ok", "sim_no_clinical_permission_required"
            }
        elif primary_source in {"activity", "supervision"}:
            actual_attendable = False
        elif primary_source == "student":
            actual_attendable = False
        elif primary_source == "undetermined":
            actual_attendable = None
        elif view["time_state"] == "upcoming":
            actual_attendable = None
        else:
            actual_attendable = True

        ward_fault = primary_source in {"activity", "supervision"}
        student_fault = any(f["source"] == "student" for f in factors) and rstatus != "no_show"
        if completed:
            route = "fulfilled"
            compensation_eligible = False
        elif rstatus == "no_show":
            route = "student_application"
            compensation_eligible = False
        elif ward_fault and not student_fault:
            route = "priority_compensation"
            compensation_eligible = True
        elif ward_fault and student_fault:
            route = "coordinator_review_mixed_cause"
            compensation_eligible = False
        elif primary_source == "student":
            route = "student_application"
            compensation_eligible = False
        elif primary_source == "undetermined":
            route = "evidence_review"
            compensation_eligible = False
        else:
            route = "pending_or_secured"
            compensation_eligible = False

        records.append({
            "student": sid,
            "course": student.get("course"),
            "original_rotation": student.get("rotation"),
            "student_deadline": student.get("deadline"),
            "apply_order": student.get("apply_order"),
            "opportunity": oid,
            "opportunity_rotation": opp.get("rotation"),
            "activity": opp.get("activity"),
            "scenario": opp.get("scenario"),
            "mode": opp.get("mode"),
            "day": opp.get("day"),
            "begin": opp.get("begin"),
            "end": opp.get("end"),
            "place": opp.get("place"),
            "start_abs": start,
            "end_abs": end,
            "time_state": view["time_state"],
            "notified": True,
            "was_notified": True,
            "can_arrive": arrival["feasible"],
            "present": completed,
            "was_present": completed,
            "was_refused": rstatus == "refused",
            "confirmed_absent": rstatus == "no_show",
            "accepted": ann.get("status") == "accepted" or rstatus == "held",
            "sent_at": ann.get("sent_at"),
            "announcement_status": ann.get("status"),
            "receipt_id": receipt["id"] if receipt else None,
            "receipt_status": rstatus,
            "receipt_at": receipt["received_at"] if receipt else None,
            "receipt_supersedes": receipt.get("supersedes") if receipt else None,
            "receipt_conflict_ids": ",".join(receipt.get("conflict_ids", [])) if receipt else "",
            "schedule_feasible": arrival["feasible"],
            "schedule_reason": arrival["reason"],
            "arrival_origin": arrival.get("origin"),
            "travel_minutes": arrival.get("travel_minutes"),
            "earliest_arrival": arrival.get("earliest_arrival"),
            "supervision_ok": sup["ok"],
            "supervision_reason": sup["reason"],
            "qualified_teachers": ",".join(sup.get("qualified", [])),
            "permission_status": perm["status"],
            "permission_allowed": perm.get("allowed"),
            "actual_permission_received_at": (perm.get("row") or {}).get("received_at") if perm.get("row") else None,
            "planned_permission_allowed": original_permission(permissions=bundle.get("permission", []), opp=opp).get("allowed"),
            "planned_attendable": planned_attendable,
            "actual_attendable": actual_attendable,
            "completed": completed,
            "loss_source": primary_source,
            "loss_source_zh": SOURCE_LABELS.get(primary_source, primary_source),
            "loss_reason": primary_reason,
            "loss_reason_zh": REASON_LABELS.get(primary_reason, primary_reason),
            "factors": factors,
            "compensation_route": route,
            "compensation_eligible": compensation_eligible,
            "dedupe_key": f"{sid}|{opp.get('activity')}",
            "overlap_with": [],
            "metric_representative": True,
            "warnings": [],
        })

    _attribute_capacity_losses(records, opp_views)
    _annotate_overlaps(records, opps)
    event_claims = _event_claims(records)
    activity_audit = _activity_audit(records)
    rotation_metrics = _rotation_metrics(records)
    return {
        "as_of": evidence_as_of,
        "now": now,
        "records": records,
        "event_claims": event_claims,
        "activity_audit": activity_audit,
        "opportunity_views": opp_views,
        "rotation_metrics": rotation_metrics,
    }


def _event_claims(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """同一临床事件号只形成一次学分/完成主张，防止重复上报。"""
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for r in records:
        if r.get("data_error") or not r.get("activity"):
            continue
        groups[(r["student"], r["activity"])].append(r)
    claims = []
    for (sid, activity), rows in sorted(groups.items()):
        completed_rows = [r for r in rows if r.get("completed")]
        claims.append({
            "student": sid,
            "activity": activity,
            "opportunities": sorted(r["opportunity"] for r in rows),
            "receipt_ids": [r.get("receipt_id") for r in rows if r.get("receipt_id")],
            "completed": bool(completed_rows),
            "completion_counted_once": bool(completed_rows),
            "counted_opportunity": completed_rows[0]["opportunity"] if completed_rows else None,
        })
    return claims


def _activity_audit(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in records:
        if not r.get("data_error") and r.get("activity"):
            groups[r["activity"]].append(r)
    rows = []
    for activity, rs in sorted(groups.items()):
        statuses = sorted({r.get("receipt_status") or "missing" for r in rs})
        has_present = any(r.get("completed") for r in rs)
        has_cancel = any(r.get("receipt_status") == "cancelled" for r in rs)
        if has_present and has_cancel:
            interpretation = "activity_occurred_but_some_student_seats_were_cancelled_or_evidence_conflicts"
        elif has_present:
            interpretation = "occurred"
        elif all(r.get("receipt_status") == "cancelled" for r in rs if r.get("receipt_status")) and has_cancel:
            interpretation = "cancelled"
        else:
            interpretation = "no_completion_claim"
        rows.append({
            "activity": activity,
            "opportunities": sorted({r["opportunity"] for r in rs}),
            "students": sorted({r["student"] for r in rs}),
            "receipt_statuses": statuses,
            "interpretation": interpretation,
            "idempotency_rule": "同一学生+activity只计一次完成；改派后的新activity另计",
        })
    return rows


def _attribute_capacity_losses(records: list[dict[str, Any]], views: dict[str, dict[str, Any]]) -> None:
    """用已到场证据推断容量/许可已满时，另一名学生失去机会。"""
    present_global: dict[tuple[str, str], set[str]] = {}
    for view in views.values():
        opp = view["opportunity"]
        key = (opp["activity"], opp["mode"])
        present_global.setdefault(key, set()).update(view["present_students"])

    for r in records:
        if r.get("data_error") or r.get("completed"):
            continue
        if r.get("receipt_status") in {"cancelled", "refused", "no_show"}:
            continue
        if r.get("loss_source") != "undetermined":
            continue
        view = views[r["opportunity"]]
        opp = view["opportunity"]
        cap = int(opp.get("capacity") or 0)
        if cap and len(view["present_students"]) >= cap:
            reason = "physical_capacity_filled_by_present_student"
        else:
            allowed = view["permission"].get("allowed")
            key = (opp["activity"], opp["mode"])
            if allowed is not None and len(present_global.get(key, set())) >= int(allowed):
                reason = "permission_capacity_filled_by_present_student"
            else:
                continue
        r["loss_source"] = "activity"
        r["loss_source_zh"] = SOURCE_LABELS["activity"]
        r["loss_reason"] = reason
        r["loss_reason_zh"] = REASON_LABELS[reason]
        r["actual_attendable"] = False
        r["compensation_route"] = "priority_compensation"
        r["compensation_eligible"] = True
        r["factors"].append({"source": "activity", "reason": reason})


def _annotate_overlaps(records: list[dict[str, Any]], opps: dict[str, dict[str, Any]]) -> None:
    by_student: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in records:
        if r.get("data_error"):
            continue
        by_student[r["student"]].append(r)

    priority = {"present": 5, "held": 4, "accepted": 4, "no_show": 2, "cancelled": 1, "refused": 1}
    for rows in by_student.values():
        for a in rows:
            for b in rows:
                if a["opportunity"] >= b["opportunity"]:
                    continue
                if overlaps(a["start_abs"], a["end_abs"], b["start_abs"], b["end_abs"]):
                    a["overlap_with"].append(b["opportunity"])
                    b["overlap_with"].append(a["opportunity"])

        # 对每个连通重叠簇选一个主计量代表，避免把同一时段两个可选机会算成可同时完成。
        clusters: list[set[str]] = []
        graph = {r["opportunity"]: set(r["overlap_with"]) for r in rows}
        seen: set[str] = set()
        for oid in graph:
            if oid in seen or not graph[oid]:
                continue
            stack = [oid]
            cluster: set[str] = set()
            while stack:
                cur = stack.pop()
                if cur in cluster:
                    continue
                cluster.add(cur)
                stack.extend(graph[cur] - cluster)
            seen |= cluster
            clusters.append(cluster)

        by_id = {r["opportunity"]: r for r in rows}
        for cluster in clusters:
            candidates = [by_id[oid] for oid in cluster]
            candidates.sort(key=lambda r: (
                0 if r["completed"] else -priority.get(r.get("receipt_status") or r.get("announcement_status"), 0),
                0 if r["actual_attendable"] is not False else 1,
                r["opportunity"],
            ), reverse=False)
            # 上面排序需要 present 优先；用显式分数更稳妥。
            def score(r: dict[str, Any]) -> tuple[int, int, str]:
                return (
                    1 if r["completed"] else 0,
                    priority.get(r.get("receipt_status") or "", priority.get(r.get("announcement_status") or "", 0)),
                    r["opportunity"],
                )
            chosen = max(candidates, key=score)
            for r in candidates:
                if r is not chosen:
                    r["metric_representative"] = False
                    r["warnings"].append("same_time_alternative_not_double_counted")
            chosen["warnings"].append("same_time_alternative_representative")


def _rotation_metrics(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in records:
        grouped[r.get("original_rotation") or r.get("opportunity_rotation") or "UNKNOWN"].append(r)

    result = []
    for rotation, rows in sorted(grouped.items()):
        metric_rows = [r for r in rows if r.get("metric_representative", True)]
        planned_bookings = len(metric_rows)
        planned = sum(1 for r in metric_rows if r.get("planned_attendable"))
        actual = sum(1 for r in metric_rows if r.get("actual_attendable") is True)
        completed = sum(1 for r in metric_rows if r.get("completed"))
        unknown_actual = sum(1 for r in metric_rows if r.get("actual_attendable") is None and r.get("time_state") == "past")
        upcoming = sum(1 for r in metric_rows if r.get("time_state") == "upcoming")
        sources = defaultdict(int)
        reasons = defaultdict(int)
        factor_sources = defaultdict(int)
        factor_reasons = defaultdict(int)
        routes = defaultdict(int)
        for r in metric_rows:
            if not r.get("completed") and r.get("loss_source") not in {"none", "pending"}:
                sources[r["loss_source"]] += 1
                reasons[r["loss_reason"]] += 1
            for factor in r.get("factors", []):
                factor_sources[factor["source"]] += 1
                factor_reasons[factor["reason"]] += 1
            routes[r["compensation_route"]] += 1
        result.append({
            "rotation": rotation,
            "announcement_records": len(rows),
            "metric_records": len(metric_rows),
            "planned_bookings": planned_bookings,
            "planned_attendable": planned,
            "actual_attendable": actual,
            "completed": completed,
            "actual_minus_completed_gap": actual - completed,
            "actual_unknown_past": unknown_actual,
            "upcoming_records": upcoming,
            "loss_supervision": sources.get("supervision", 0),
            "loss_activity": sources.get("activity", 0),
            "loss_student": sources.get("student", 0),
            "loss_undetermined": sources.get("undetermined", 0),
            "loss_pending": sources.get("pending", 0),
            "primary_reasons": dict(reasons),
            "all_factor_sources": dict(factor_sources),
            "all_factor_reasons": dict(factor_reasons),
            "reasons": dict(reasons),
            "routes": dict(routes),
        })
    return result
