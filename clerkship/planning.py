"""整轮补学安排与全局瓶颈优先匹配。"""
from __future__ import annotations

from typing import Any, Iterable

from .timeutil import interval, arrival_check

try:  # 锁定环境提供 scipy；缺失时仍可使用内置小规模回退。
    import numpy as np
    from scipy.optimize import Bounds, LinearConstraint, milp
    HAVE_SCIPY = True
except Exception:  # pragma: no cover - 最小环境兜底
    HAVE_SCIPY = False
    np = None
    milp = None
    Bounds = None
    LinearConstraint = None


UNRESOLVED_LABELS = {
    "awaiting_final_evidence_before_compensation": "最终回执/许可证据未齐，暂不能按补偿发出",
    "accepted_appointment_protected_requires_one_student_consent_to_swap": "已有受保护预约；不能自动释放，须先征得学生一次换约同意",
    "no_recognized_session_before_deadline": "截止前没有课程承认的可履行方式（模拟替代不适用）",
    "no_matching_session_before_deadline": "截止前没有匹配场景的可预约场次",
    "capacity_or_deadline_blocks_all_slots": "所有合格时段均被容量/截止日限制",
    "eligible_slot_allocated_to_higher_priority_need_or_blocked": "合格时段已按保障顺序分给更高优先级缺口，或受保护安排阻挡",
}


def _active_blocks(accounting: dict[str, Any], sid: str, *, remove_opp: str | None = None,
                   add_blocks: Iterable[dict[str, Any]] = ()) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    for r in accounting["records"]:
        if r["student"] != sid or r.get("data_error"):
            continue
        if r["opportunity"] == remove_opp:
            continue
        if r.get("receipt_status") in {"cancelled", "refused", "present", "no_show"}:
            # 已结束事实不阻挡未来候选；同日已结束段由 busy/时间判断也无害，
            # 但 present/no_show 不是未来占位。
            if r.get("time_state") != "upcoming":
                continue
        if r.get("time_state") == "past":
            continue
        blocks.append({
            "day": r["day"],
            "start_abs": r["start_abs"],
            "end_abs": r["end_abs"],
            "location": r.get("place"),
            "ref": r["opportunity"],
            "kind": "accepted_appointment" if r.get("announcement_status") == "accepted" or r.get("receipt_status") == "held" else "notified_alternative",
        })
    blocks.extend(add_blocks)
    return blocks


def evaluate_candidates(
    need: dict[str, Any],
    bundle: dict[str, Any],
    accounting: dict[str, Any],
    *,
    remove_opp: str | None = None,
    add_blocks: Iterable[dict[str, Any]] = (),
    capacity_adjust: dict[str, int] | None = None,
    notice_time: int | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """列出一个缺口的全部合格/不合格时段及原因。"""
    sid = need["student"]
    student = next(s for s in bundle["student"] if s["id"] == sid)
    opps = {o["id"]: o for o in bundle["opportunity"]}
    views = accounting["opportunity_views"]
    busy = bundle["busy"]
    travel = bundle["travel"]
    capacity_adjust = capacity_adjust or {}

    active_oids = {
        r["opportunity"] for r in accounting["records"]
        if r["student"] == sid and r.get("receipt_status") not in {"cancelled", "refused"}
    }
    candidates: list[dict[str, Any]] = []
    evaluations: list[dict[str, Any]] = []

    for oid, view in sorted(views.items()):
        opp = view["opportunity"]
        if opp["scenario"] != need["scenario"]:
            continue
        reasons: list[str] = []
        if opp["day"] > need["deadline"]:
            reasons.append("after_deadline")
        if opp["mode"] == "sim" and not need["simulation_allowed"]:
            reasons.append("simulation_substitution_not_recognized")
        if not view["supervision"]["ok"]:
            reasons.append(view["supervision"]["reason"])
        if view["permission"]["status"] not in {"permission_ok", "sim_no_clinical_permission_required"}:
            reasons.append(view["permission"]["status"])
        available_capacity = max(0, view["remaining_capacity"] + capacity_adjust.get(oid, 0))
        if available_capacity <= 0:
            reasons.append("capacity_exhausted")
        global_perm = view.get("permission_remaining_global")
        if global_perm is not None:
            perm_key = (opp["activity"], opp["mode"])
            perm_delta = sum(
                delta for other_oid, delta in capacity_adjust.items()
                if (
                    accounting["opportunity_views"][other_oid]["opportunity"]["activity"],
                    accounting["opportunity_views"][other_oid]["opportunity"]["mode"],
                ) == perm_key
            )
            if max(0, int(global_perm) + perm_delta) <= 0:
                reasons.append("permission_capacity_exhausted")
        if view["time_state"] != "upcoming":
            reasons.append(f"time_{view['time_state']}")
        if oid in active_oids and oid != remove_opp:
            reasons.append("student_already_booked_here")

        blocks = _active_blocks(accounting, sid, remove_opp=remove_opp, add_blocks=add_blocks)
        # 对已过/进行中的场次，time_state 已给出不可预约原因；通知时点检查只用于未来场。
        effective_notice_time = notice_time if view["time_state"] == "upcoming" else None
        arrival = arrival_check(
            student, opp, busy, travel,
            sent_at=effective_notice_time, extra_blocks=blocks,
        )
        if not arrival["feasible"]:
            reasons.append(arrival["reason"])

        record = {
            "need_id": need["need_id"],
            "student": sid,
            "opportunity": oid,
            "activity": opp["activity"],
            "rotation": opp["rotation"],
            "scenario": opp["scenario"],
            "mode": opp["mode"],
            "day": opp["day"],
            "begin": opp["begin"],
            "end": opp["end"],
            "place": opp["place"],
            "start_abs": view["start_abs"],
            "end_abs": view["end_abs"],
            "remaining_capacity": available_capacity,
            "travel_minutes": arrival.get("travel_minutes"),
            "schedule_feasible": arrival["feasible"],
            "eligible": not reasons,
            "reasons": reasons,
        }
        evaluations.append(record)
        if not reasons:
            same_rotation_bonus = 15 if opp["rotation"] == need["original_rotation"] else 0
            real_bonus = 5 if opp["mode"] == "real" else 0
            travel_penalty = (arrival.get("travel_minutes") or 0) * 0.1
            early_bonus = max(0, 10 - int(opp["day"]))
            score = round(50 + same_rotation_bonus + real_bonus + early_bonus - travel_penalty, 2)
            record["slot_score"] = score
            candidates.append(record)

    return candidates, evaluations


def _milp_solve(variables: list[dict[str, Any]], needs_by_id: dict[str, dict[str, Any]],
                capacities: dict[str, int], fixed: dict[str, int], objective_need: str | None = None,
                score_objective: bool = False,
                permission_capacities: dict[tuple[str, str], int] | None = None) -> list[int] | None:
    if not variables:
        return []
    if not HAVE_SCIPY:  # pragma: no cover
        return _fallback_solve(variables, needs_by_id, capacities, fixed, objective_need, score_objective)

    n = len(variables)
    rows: list[np.ndarray] = []
    lbs: list[float] = []
    ubs: list[float] = []

    def add_constraint(indices: list[int], lb: float | None = None, ub: float | None = None,
                       equal: float | None = None) -> None:
        row = np.zeros(n)
        for i in indices:
            row[i] = 1
        rows.append(row)
        if equal is not None:
            lbs.append(equal)
            ubs.append(equal)
        else:
            lbs.append(-np.inf if lb is None else lb)
            ubs.append(np.inf if ub is None else ub)

    by_need: dict[str, list[int]] = {}
    by_opp: dict[str, list[int]] = {}
    by_perm: dict[tuple[str, str], list[int]] = {}
    by_student_opp: dict[tuple[str, str], list[int]] = {}
    for i, v in enumerate(variables):
        by_need.setdefault(v["need_id"], []).append(i)
        by_opp.setdefault(v["opportunity"], []).append(i)
        perm_key = (v.get("activity"), v.get("mode"))
        if permission_capacities is not None and perm_key in permission_capacities:
            by_perm.setdefault(perm_key, []).append(i)
        by_student_opp.setdefault((v["student"], v["opportunity"]), []).append(i)

    for need_id, indices in by_need.items():
        add_constraint(indices, ub=1)
    for need_id, value in fixed.items():
        if need_id in by_need:
            add_constraint(by_need[need_id], equal=float(value))
        elif value != 0:
            return None
    for oid, indices in by_opp.items():
        cap = capacities.get(oid, 0)
        add_constraint(indices, ub=float(cap))
    for perm_key, indices in by_perm.items():
        add_constraint(indices, ub=float(permission_capacities.get(perm_key, 0)))
    for key, indices in by_student_opp.items():
        if len(indices) > 1:
            add_constraint(indices, ub=1)

    # 同一学生的重叠时段不能同时选择。
    for sid in {v["student"] for v in variables}:
        sv = [(i, v) for i, v in enumerate(variables) if v["student"] == sid]
        for pos, (i, a) in enumerate(sv):
            for j, b in sv[pos + 1:]:
                if a["opportunity"] == b["opportunity"]:
                    continue
                if max(a["start_abs"], b["start_abs"]) < min(a["end_abs"], b["end_abs"]):
                    add_constraint([i, j], ub=1)

    A = np.vstack(rows) if rows else np.empty((0, n))
    constraints = LinearConstraint(A, np.array(lbs), np.array(ubs))
    integrality = np.ones(n)
    bounds = Bounds(np.zeros(n), np.ones(n))

    if score_objective:
        c = np.array([-float(v.get("slot_score", 50)) for v in variables])
    elif objective_need is not None:
        c = np.zeros(n)
        for i, v in enumerate(variables):
            if v["need_id"] == objective_need:
                c[i] = -1
        # 轻微分数偏好不改变“完成当前缺口”的主目标。
        c += np.array([-0.0001 * float(v.get("slot_score", 50)) for v in variables])
    else:
        c = np.zeros(n)

    result = milp(c=c, integrality=integrality, bounds=bounds, constraints=constraints,
                  options={"disp": False, "time_limit": 30})
    if not result.success and result.x is None:
        return None
    x = np.rint(result.x).astype(int)
    return [i for i, value in enumerate(x) if value == 1]


def _fallback_solve(variables, needs_by_id, capacities, fixed, objective_need=None, score_objective=False):  # pragma: no cover
    # 极小数据的确定性贪心；当前运行环境有 scipy，因此主路径是 MILP。
    used: dict[str, int] = {}
    chosen: list[int] = []
    student_times: dict[str, list[tuple[int, int]]] = {}
    fixed_values = dict(fixed)
    for need_id, value in fixed_values.items():
        if value == 0:
            continue
    order = sorted(range(len(variables)), key=lambda i: -variables[i].get("slot_score", 0))
    for i in order:
        v = variables[i]
        if fixed_values.get(v["need_id"]) == 0:
            continue
        if used.get(v["opportunity"], 0) >= capacities.get(v["opportunity"], 0):
            continue
        intervals = student_times.setdefault(v["student"], [])
        if any(max(v["start_abs"], s) < min(v["end_abs"], e) for s, e in intervals):
            continue
        chosen.append(i)
        used[v["opportunity"]] = used.get(v["opportunity"], 0) + 1
        intervals.append((v["start_abs"], v["end_abs"]))
    return chosen


def solve_stage(
    needs: list[dict[str, Any]],
    bundle: dict[str, Any],
    accounting: dict[str, Any],
    *,
    allowed_routes: set[str] | None = None,
    capacity_adjust: dict[str, int] | None = None,
    candidate_overrides: dict[str, tuple[list[dict[str, Any]], list[dict[str, Any]]]] | None = None,
    priority_key: Any = None,
    remove_opp_by_student: dict[str, str] | None = None,
    extra_blocks_by_student: dict[str, list[dict[str, Any]]] | None = None,
    notice_time: int | None = None,
) -> dict[str, Any]:
    capacity_adjust = capacity_adjust or {}
    views = accounting["opportunity_views"]
    capacities = {
        oid: max(0, view["remaining_capacity"] + capacity_adjust.get(oid, 0))
        for oid, view in views.items()
    }
    permission_capacities: dict[tuple[str, str], int] = {}
    for view in views.values():
        remaining_global = view.get("permission_remaining_global")
        if remaining_global is not None:
            opp = view["opportunity"]
            permission_capacities[(opp["activity"], opp["mode"])] = int(remaining_global)
    for oid, delta in capacity_adjust.items():
        opp = views[oid]["opportunity"]
        key = (opp["activity"], opp["mode"])
        if key in permission_capacities:
            permission_capacities[key] = max(0, permission_capacities[key] + int(delta))

    stage_needs = [
        n for n in needs
        if allowed_routes is None or n["route"] in allowed_routes
    ]
    all_candidates: list[dict[str, Any]] = []
    evaluations: list[dict[str, Any]] = []
    candidates_by_need: dict[str, list[dict[str, Any]]] = {}
    for need in stage_needs:
        if candidate_overrides and need["need_id"] in candidate_overrides:
            candidates, evals = candidate_overrides[need["need_id"]]
        else:
            sid = need["student"]
            candidates, evals = evaluate_candidates(
                need, bundle, accounting,
                capacity_adjust=capacity_adjust,
                remove_opp=(remove_opp_by_student or {}).get(sid),
                add_blocks=(extra_blocks_by_student or {}).get(sid, ()),
                notice_time=notice_time,
            )
        candidates_by_need[need["need_id"]] = candidates
        all_candidates.extend(candidates)
        evaluations.extend(evals)

    # 变量需要带 need 的优先级信息。
    variables = []
    for cand in all_candidates:
        variables.append({**cand})

    needs_by_id = {n["need_id"]: n for n in stage_needs}
    if priority_key is None:
        def priority_key(n: dict[str, Any]):
            return (
                n["deadline"],
                len(candidates_by_need.get(n["need_id"], [])),
                n.get("apply_order", 9999),
                n["student"],
                n.get("obligation_order", 0),
                n.get("gap_index", 0),
            )

    ordered_needs = sorted(stage_needs, key=priority_key)
    fixed: dict[str, int] = {}
    fulfillment: dict[str, int] = {}

    for need in ordered_needs:
        nid = need["need_id"]
        if not candidates_by_need.get(nid):
            fixed[nid] = 0
            fulfillment[nid] = 0
            continue
        selected = _milp_solve(
            variables, needs_by_id, capacities, fixed,
            objective_need=nid, permission_capacities=permission_capacities,
        )
        if selected is None:
            best = 0
        else:
            best = 1 if any(variables[i]["need_id"] == nid for i in selected) else 0
        fixed[nid] = best
        fulfillment[nid] = best

    selected_indices = _milp_solve(
        variables, needs_by_id, capacities, fixed,
        score_objective=True, permission_capacities=permission_capacities,
    ) or []
    assignments = [variables[i] for i in selected_indices]
    return {
        "assignments": assignments,
        "evaluations": evaluations,
        "candidates_by_need": candidates_by_need,
        "fulfillment": fulfillment,
        "ordered_needs": [n["need_id"] for n in ordered_needs],
        "capacities": capacities,
    }


def plan_remediation(
    accounting: dict[str, Any],
    needs: list[dict[str, Any]],
    bundle: dict[str, Any],
    *,
    consents: Iterable[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """生成基线安排、未决缺口和换约征询。

    consents 可传 ``{"student": "S4", "from": "O6", "to": "O10"}``，表示学生已
    主动同意一次换约；未传时，旧预约容量保持保护，不自动变空位。
    """
    consents = list(consents or [])
    if len({c["student"] for c in consents}) != len(consents):
        raise ValueError("每名学生只能主动同意一次换约")

    students = {s["id"]: s for s in bundle.get("student", [])}
    obligations = {(o["course"], o["scenario"]): o for o in bundle.get("obligation", [])}
    records_by_student_opp = {
        (r["student"], r["opportunity"]): r
        for r in accounting["records"] if not r.get("data_error")
    }

    # 已获同意的换约：释放旧容量，并把新时段作为该学生的确定占位。
    capacity_adjust: dict[str, int] = {}
    consented_assignments: list[dict[str, Any]] = []
    remove_opp_by_student: dict[str, str] = {}
    extra_blocks_by_student: dict[str, list[dict[str, Any]]] = {}
    consented_need_ids: set[str] = set()
    consent_errors: list[dict[str, Any]] = []

    for consent in consents:
        sid, from_oid, to_oid = consent["student"], consent["from"], consent["to"]
        old_record = records_by_student_opp.get((sid, from_oid))
        if old_record is None:
            consent_errors.append({**consent, "error": "original_appointment_not_found"})
            continue
        student = students[sid]
        obligation = obligations[(student["course"], old_record["scenario"])]
        swap_need = {
            "need_id": f"CONSENT-{sid}-{from_oid}-{to_oid}",
            "student": sid,
            "course": student["course"],
            "original_rotation": student["rotation"],
            "scenario": old_record["scenario"],
            "deadline": student["deadline"],
            "apply_order": student["apply_order"],
            "simulation_allowed": bool(obligation["simulation_allowed"]),
        }
        candidates, _ = evaluate_candidates(
            swap_need, bundle, accounting, remove_opp=from_oid,
            notice_time=accounting.get("now"),
        )
        candidate = next((c for c in candidates if c["opportunity"] == to_oid), None)
        if candidate is None:
            consent_errors.append({**consent, "error": "requested_swap_slot_not_feasible_or_recognized"})
            continue

        capacity_adjust[from_oid] = capacity_adjust.get(from_oid, 0) + 1
        capacity_adjust[to_oid] = capacity_adjust.get(to_oid, 0) - 1
        remove_opp_by_student[sid] = from_oid
        extra_blocks_by_student[sid] = [{
            "day": candidate["day"],
            "start_abs": candidate["start_abs"],
            "end_abs": candidate["end_abs"],
            "location": candidate["place"],
            "ref": to_oid,
            "kind": "consented_swap",
        }]
        matching_need = next((
            n for n in needs
            if n["student"] == sid and n["scenario"] == old_record["scenario"]
            and any(h["opportunity"] == from_oid for h in n.get("at_risk_holds", []))
        ), None)
        if matching_need:
            consented_need_ids.add(matching_need["need_id"])
        consented_assignments.append({
            **candidate,
            "assignment_id": f"CS-{sid}-{from_oid}-{to_oid}",
            "need_id": matching_need["need_id"] if matching_need else f"SECURED-{sid}-{old_record['scenario']}",
            "status": "consented_swap_confirmed",
            "student": sid,
            "original_rotation": student["rotation"],
            "fills_course": student["course"],
            "fills_scenario": old_record["scenario"],
            "gap_description": f"{student['course']}/{old_record['scenario']} 已同意换约",
            "simulation_recognized": candidate["mode"] != "sim" or swap_need["simulation_allowed"],
            "deadline_day": student["deadline"],
            "route": "consented_swap",
            "compensation_eligible": False,
            "ward_loss_basis": matching_need.get("ward_loss_basis", []) if matching_need else [],
            "student_application_basis": [],
            "selection_basis": "学生已主动同意一次换约；旧位在同意前保持保护",
        })

    stage1_needs = [
        n for n in needs
        if n["route"] in {"priority_compensation", "standard_provision"}
        and n["need_id"] not in consented_need_ids
    ]
    stage1 = solve_stage(
        stage1_needs,
        bundle, accounting,
        capacity_adjust=capacity_adjust,
        remove_opp_by_student=remove_opp_by_student,
        extra_blocks_by_student=extra_blocks_by_student,
        notice_time=accounting.get("now"),
    )
    used: dict[str, int] = {}
    for a in stage1["assignments"]:
        used[a["opportunity"]] = used.get(a["opportunity"], 0) + 1

    # 第二阶段：已确认缺席走自行申请规则，只使用第一阶段保障后的余量。
    app_needs = [n for n in needs if n["route"] == "student_application"]
    # 通过 capacity_adjust 扣除一阶段用量。
    app_adjust = dict(capacity_adjust)
    for oid, count in used.items():
        app_adjust[oid] = app_adjust.get(oid, 0) - count
    stage2 = solve_stage(
        app_needs, bundle, accounting,
        allowed_routes={"student_application"},
        capacity_adjust=app_adjust,
        remove_opp_by_student=remove_opp_by_student,
        extra_blocks_by_student=extra_blocks_by_student,
        notice_time=accounting.get("now"),
        priority_key=lambda n: (n.get("apply_order", 9999), n["deadline"], n["student"], n.get("obligation_order", 0)),
    )

    assignments = list(consented_assignments)
    for idx, a in enumerate(stage1["assignments"] + stage2["assignments"], start=len(assignments) + 1):
        need = next(n for n in needs if n["need_id"] == a["need_id"])
        route = need["route"]
        assignments.append({
            "assignment_id": f"R{idx:03d}-{a['student']}-{a['opportunity']}",
            "status": "proposed_ready_for_coordinator_review",
            "student": a["student"],
            "original_rotation": need["original_rotation"],
            "need_id": a["need_id"],
            "fills_course": need["course"],
            "fills_scenario": a["scenario"],
            "gap_description": f"{need['course']}/{a['scenario']} 第{need['gap_index']}项必修缺口",
            "opportunity": a["opportunity"],
            "activity": a["activity"],
            "offering_rotation": a["rotation"],
            "mode": a["mode"],
            "simulation_recognized": a["mode"] != "sim" or need["simulation_allowed"],
            "day": a["day"],
            "begin": a["begin"],
            "end": a["end"],
            "place": a["place"],
            "deadline_day": need["deadline"],
            "slot_score": a.get("slot_score"),
            "route": route,
            "compensation_eligible": need["compensation_eligible"],
            "compensation_review_required": need.get("compensation_review_required", False),
            "mixed_loss_basis": need.get("mixed_loss_basis", []),
            "ward_loss_basis": need["ward_loss_basis"],
            "student_application_basis": need["no_show_basis"],
            "selection_basis": "整轮瓶颈优先：截止日→唯一合格时段→申请顺序；评分仅作同条件平局参考",
        })

    unresolved = _build_unresolved(needs, stage1, stage2, accounting, bundle, assignments)
    do_not_send = _build_do_not_send(accounting, needs, assignments)
    swaps = propose_swaps(accounting, needs, bundle, stage1, stage2)
    release_consultations = _redundant_hold_consultations(accounting, bundle)
    protected_appointments = _protected_appointments(accounting)
    for item in release_consultations:
        do_not_send.append({
            "student": item["student"],
            "opportunity": item["opportunity"],
            "scope": item["fills"],
            "code": "redundant_accepted_hold_do_not_auto_release",
            "detail": item["basis"],
        })

    return {
        "assignments": assignments,
        "consented_swaps": consented_assignments,
        "consent_errors": consent_errors,
        "unresolved": unresolved,
        "slot_evaluations": stage1["evaluations"] + stage2["evaluations"],
        "do_not_send": do_not_send,
        "protected_appointments": protected_appointments,
        "swap_consultations": swaps,
        "release_consultations": release_consultations,
        "stage1_fulfillment": stage1["fulfillment"],
        "stage2_fulfillment": stage2["fulfillment"],
        "priority_order": stage1["ordered_needs"],
    }


def _build_unresolved(needs, stage1, stage2, accounting, bundle, assignments) -> list[dict[str, Any]]:
    assigned_need_ids = {a["need_id"] for a in assignments}
    rows: list[dict[str, Any]] = []
    evals_by_need: dict[str, list[dict[str, Any]]] = {}
    for e in stage1["evaluations"] + stage2["evaluations"]:
        evals_by_need.setdefault(e["need_id"], []).append(e)

    for need in needs:
        if need["need_id"] in assigned_need_ids:
            continue
        if need["route"] == "fulfilled_or_secured":
            continue
        evals = evals_by_need.get(need["need_id"], [])
        reason_counts: dict[str, int] = {}
        for e in evals:
            for reason in e["reasons"]:
                reason_counts[reason] = reason_counts.get(reason, 0) + 1
        if need["route"] == "evidence_review":
            primary = "awaiting_final_evidence_before_compensation"
        elif need["route"] == "protected_hold_requires_swap":
            primary = "accepted_appointment_protected_requires_one_student_consent_to_swap"
        elif not evals:
            # 没有任何同场景机会通过基础匹配。
            if need["simulation_allowed"] is False:
                primary = "no_recognized_session_before_deadline"
            else:
                primary = "no_matching_session_before_deadline"
        elif reason_counts.get("capacity_exhausted") and all("capacity_exhausted" in e["reasons"] or "after_deadline" in e["reasons"] for e in evals):
            primary = "capacity_or_deadline_blocks_all_slots"
        else:
            primary = "eligible_slot_allocated_to_higher_priority_need_or_blocked"
        rows.append({
            "need_id": need["need_id"],
            "student": need["student"],
            "original_rotation": need["original_rotation"],
            "course": need["course"],
            "scenario": need["scenario"],
            "deadline": need["deadline"],
            "apply_order": need["apply_order"],
            "route": need["route"],
            "compensation_eligible": need["compensation_eligible"],
            "primary_reason": primary,
            "primary_reason_zh": UNRESOLVED_LABELS.get(primary, primary),
            "blocking_reason_counts": reason_counts,
            "ward_loss_basis": need["ward_loss_basis"],
            "no_show_basis": need["no_show_basis"],
            "unknown_basis": need["unknown_basis"],
            "at_risk_holds": need["at_risk_holds"],
            "candidate_count": len(evals),
        })
    return rows


def _build_do_not_send(accounting, needs, assignments) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    assigned_student_scenario = {(a["student"], a["fills_scenario"]) for a in assignments}
    for need in needs:
        key = (need["student"], need["scenario"])
        if need["route"] == "fulfilled_or_secured":
            rows.append({
                "student": need["student"],
                "scope": key[1],
                "code": "gap_already_completed_or_secured",
                "detail": "已有有效完成或受保护且可履行的预约，不再发同缺口补学邀请",
            })
        elif key in assigned_student_scenario:
            rows.append({
                "student": need["student"],
                "scope": key[1],
                "code": "new_assignment_already_selected",
                "detail": "本轮已生成安排，不重复发同一缺口邀请",
            })

    for oid, view in accounting["opportunity_views"].items():
        if view["time_state"] != "upcoming":
            continue
        if view["not_bookable_reasons"]:
            rows.append({
                "student": "*",
                "opportunity": oid,
                "scope": view["opportunity"]["scenario"],
                "code": "opportunity_not_to_issue",
                "detail": ",".join(view["not_bookable_reasons"]),
            })
        if view["protected_students"]:
            rows.append({
                "student": ",".join(view["protected_students"]),
                "opportunity": oid,
                "scope": view["opportunity"]["scenario"],
                "code": "accepted_appointment_protected",
                "detail": "已接受预约不自动变空位；如需换约，只能向学生发起一次征询",
            })
    return rows


def _protected_appointments(accounting: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for r in accounting["records"]:
        accepted = r.get("announcement_status") == "accepted" or r.get("receipt_status") == "held"
        if not accepted:
            continue
        secure = (
            r.get("schedule_feasible") is True
            and r.get("supervision_ok") is True
            and r.get("permission_status") in {"permission_ok", "sim_no_clinical_permission_required"}
        )
        rows.append({
            "assignment_id": f"HELD-{r['student']}-{r['opportunity']}",
            "status": "protected_existing_appointment",
            "student": r["student"],
            "original_rotation": r.get("original_rotation"),
            "fills_course": r.get("course"),
            "fills_scenario": r.get("scenario"),
            "gap_description": f"{r.get('course')}/{r.get('scenario')} 已接受预约",
            "opportunity": r["opportunity"],
            "activity": r.get("activity"),
            "mode": r.get("mode"),
            "day": r.get("day"),
            "begin": r.get("begin"),
            "end": r.get("end"),
            "place": r.get("place"),
            "time_state": r.get("time_state"),
            "performable_with_current_data": secure,
            "schedule_reason": r.get("schedule_reason"),
            "supervision_reason": r.get("supervision_reason"),
            "permission_status": r.get("permission_status"),
            "policy": "已接受预约受保护；不得自动释放或视为空位，只能征询一次换约",
        })
    return rows


def _redundant_hold_consultations(accounting: dict[str, Any], bundle: dict[str, Any]) -> list[dict[str, Any]]:
    """新证据表明缺口已补上时，已接受预约仍受保护，只能征询是否释放/换约。"""
    obligations = {(o["course"], o["scenario"]): o for o in bundle.get("obligation", [])}
    students = {s["id"]: s for s in bundle.get("student", [])}
    completed_scenarios: dict[str, set[str]] = {}
    for r in accounting["records"]:
        if not r.get("completed"):
            continue
        student = students.get(r["student"])
        if not student:
            continue
        obligation = obligations.get((student["course"], r["scenario"]))
        sim_allowed = bool(obligation and obligation["simulation_allowed"])
        if r["mode"] == "sim" and not sim_allowed:
            continue
        completed_scenarios.setdefault(r["student"], set()).add(r["scenario"])

    rows = []
    for r in accounting["records"]:
        accepted = r.get("announcement_status") == "accepted" or r.get("receipt_status") == "held"
        if not accepted or r.get("time_state") != "upcoming":
            continue
        if r["scenario"] not in completed_scenarios.get(r["student"], set()):
            continue
        rows.append({
            "student": r["student"],
            "opportunity": r["opportunity"],
            "activity": r["activity"],
            "fills": f"{r['course']}/{r['scenario']}",
            "consult_type": "ask_whether_to_release_or_swap_redundant_hold",
            "status": "accepted_hold_remains_protected_until_student_chooses",
            "auto_released": False,
            "basis": "新回执已确认原缺口完成；但已接受预约不得由草案自动改成空位",
            "day": r["day"], "begin": r["begin"], "end": r["end"], "mode": r["mode"],
        })
    return rows


def propose_swaps(accounting, needs, bundle, baseline_stage1, baseline_stage2) -> list[dict[str, Any]]:
    """找出能消除风险或改善整轮保障的一次性换约征询。

    所有建议都只是“可征询”：在学生主动同意前，旧预约仍占容量，不会自动变成空位。
    """
    proposals: list[dict[str, Any]] = []
    students = {s["id"]: s for s in bundle.get("student", [])}
    obligations = {(o["course"], o["scenario"]): o for o in bundle.get("obligation", [])}
    baseline_assigned_ids = {a["need_id"] for a in baseline_stage1["assignments"]}

    stage1_needs = [n for n in needs if n["route"] in {"priority_compensation", "standard_provision"}]
    at_risk_need_by_hold: dict[tuple[str, str], dict[str, Any]] = {}
    for need in needs:
        for hold in need.get("at_risk_holds", []):
            at_risk_need_by_hold[(need["student"], hold["opportunity"])] = need

    holds: list[dict[str, Any]] = []
    for r in accounting["records"]:
        if r.get("data_error") or r.get("time_state") != "upcoming":
            continue
        accepted = r.get("announcement_status") == "accepted" or r.get("receipt_status") == "held"
        if accepted:
            holds.append(r)

    for old_record in holds:
        sid, old_oid = old_record["student"], old_record["opportunity"]
        at_risk_need = at_risk_need_by_hold.get((sid, old_oid))
        student = students[sid]
        obligation = obligations[(student["course"], old_record["scenario"])]
        swap_need = at_risk_need or {
            "need_id": f"HOLD-{sid}-{old_oid}",
            "student": sid,
            "course": student["course"],
            "original_rotation": student["rotation"],
            "scenario": old_record["scenario"],
            "deadline": student["deadline"],
            "apply_order": student["apply_order"],
            "simulation_allowed": bool(obligation["simulation_allowed"]),
        }
        old_at_risk = bool(at_risk_need)
        candidates, _ = evaluate_candidates(
            swap_need, bundle, accounting, remove_opp=old_oid,
            notice_time=accounting.get("now"),
        )

        for cand in candidates:
            new_oid = cand["opportunity"]
            add_blocks = [{
                "day": cand["day"], "start_abs": cand["start_abs"], "end_abs": cand["end_abs"],
                "location": cand["place"], "ref": new_oid, "kind": "conditional_swap",
            }]
            adjust = {old_oid: 1, new_oid: -1}
            excluded_id = at_risk_need["need_id"] if at_risk_need else None
            other_needs = [n for n in stage1_needs if n["need_id"] != excluded_id]
            try:
                conditional = solve_stage(
                    other_needs, bundle, accounting,
                    capacity_adjust=adjust,
                    remove_opp_by_student={sid: old_oid},
                    extra_blocks_by_student={sid: add_blocks},
                    notice_time=accounting.get("now"),
                )
            except Exception:
                continue

            order = [nid for nid in baseline_stage1["ordered_needs"] if nid != excluded_id]
            baseline_vector = tuple(baseline_stage1["fulfillment"].get(nid, 0) for nid in order)
            conditional_vector = tuple(conditional["fulfillment"].get(nid, 0) for nid in order)
            improves_round = conditional_vector > baseline_vector
            conditional_ids = {a["need_id"] for a in conditional["assignments"]}
            gained_ids = sorted(conditional_ids - baseline_assigned_ids)
            lost_ids = sorted(
                nid for nid in (baseline_assigned_ids - conditional_ids)
                if nid != excluded_id
            )
            id_to_student = {n["need_id"]: f"{n['student']}:{n['scenario']}" for n in stage1_needs}
            tradeoff = {
                "gains": [{"need_id": nid, "gap": id_to_student.get(nid, nid)} for nid in gained_ids],
                "loses_or_defers_baseline_gap": [
                    {"need_id": nid, "gap": id_to_student.get(nid, nid)} for nid in lost_ids
                ],
            }
            if not old_at_risk and not improves_round:
                continue

            released_to = [
                {"student": a["student"], "need_id": a["need_id"], "opportunity": a["opportunity"]}
                for a in conditional["assignments"]
                if a["opportunity"] == old_oid
            ]
            proposals.append({
                "student": sid,
                "one_swap_only": True,
                "from_opportunity": old_oid,
                "to_opportunity": new_oid,
                "fills": f"{swap_need['course']}/{swap_need['scenario']}",
                "status": "ask_student_for_voluntary_consent",
                "consultable": True,
                "recommended": False,
                "preferred_option_for_hold": False,
                "old_hold_at_risk": old_at_risk,
                "round_improvement": improves_round,
                "tradeoff_vs_baseline": tradeoff,
                "old_seat_stays_protected_until_consent": True,
                "new_slot": {
                    k: cand[k]
                    for k in ("day", "begin", "end", "place", "mode", "activity", "slot_score")
                },
                "conditional_capacity_after_consent": adjust,
                "released_old_slot_would_go_to": released_to,
                "conditional_other_assignments": [
                    {
                        "student": a["student"],
                        "need_id": a["need_id"],
                        "opportunity": a["opportunity"],
                    }
                    for a in conditional["assignments"]
                ],
                "benefit": (
                    "消除已接受预约的时间/资料风险"
                    if old_at_risk else
                    "在不动其他保护预约的前提下释放唯一实地/合格时段给更高优先级缺口"
                ),
                "do_not_reissue_old_opportunity_without_permission_clearance":
                    accounting["opportunity_views"][old_oid]["permission"]["status"] not in {
                        "permission_ok", "sim_no_clinical_permission_required"
                    },
                "_rank": (
                    conditional_vector,
                    len(conditional["assignments"]),
                    -len(tradeoff["loses_or_defers_baseline_gap"]),
                    float(cand.get("slot_score", 0)),
                ),
            })

    seen = set()
    unique = []
    for p in proposals:
        key = (p["student"], p["from_opportunity"], p["to_opportunity"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(p)

    best_by_hold: dict[tuple[str, str], dict[str, Any]] = {}
    for p in unique:
        hold_key = (p["student"], p["from_opportunity"])
        current = best_by_hold.get(hold_key)
        if current is None or p["_rank"] > current["_rank"]:
            best_by_hold[hold_key] = p
    for p in unique:
        if best_by_hold.get((p["student"], p["from_opportunity"])) is p:
            p["recommended"] = True
            p["preferred_option_for_hold"] = True
        p.pop("_rank", None)

    return sorted(unique, key=lambda p: (p["student"], p["from_opportunity"], not p["recommended"], p["to_opportunity"]))
