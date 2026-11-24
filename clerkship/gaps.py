"""按课程义务汇总学生缺口和补偿路径。"""
from __future__ import annotations

from collections import defaultdict
from typing import Any


def build_needs(accounting: dict[str, Any], bundle: dict[str, Any]) -> list[dict[str, Any]]:
    students = {s["id"]: s for s in bundle.get("student", [])}
    obligations = {
        (o["course"], o["scenario"]): o for o in bundle.get("obligation", [])
    }
    records_by_student: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in accounting["records"]:
        if not r.get("data_error"):
            records_by_student[r["student"]].append(r)

    needs: list[dict[str, Any]] = []
    for sid, student in sorted(students.items()):
        course = student["course"]
        for scenario_index, obligation in enumerate(
            [o for o in bundle.get("obligation", []) if o["course"] == course], start=1
        ):
            scenario = obligation["scenario"]
            required = int(obligation.get("required") or 0)
            sim_allowed = bool(obligation.get("simulation_allowed"))
            rows = [r for r in records_by_student[sid] if r["scenario"] == scenario]

            completed_real: set[str] = set()
            completed_recognized: set[str] = set()
            completed_unrecognized_sim: list[dict[str, Any]] = []
            for r in rows:
                if not r["completed"]:
                    continue
                activity = r["activity"]
                if r["mode"] == "sim" and not sim_allowed:
                    completed_unrecognized_sim.append({
                        "opportunity": r["opportunity"],
                        "activity": activity,
                        "reason": "simulation_not_recognized_for_course_scenario",
                    })
                    continue
                completed_recognized.add(activity)
                if r["mode"] == "real":
                    completed_real.add(activity)

            secured: set[str] = set()
            at_risk_holds: list[dict[str, Any]] = []
            for r in rows:
                accepted = r.get("announcement_status") == "accepted" or r.get("receipt_status") == "held"
                if not accepted or r["completed"]:
                    continue
                mode_ok = r["mode"] != "sim" or sim_allowed
                secure = (
                    mode_ok
                    and r.get("schedule_feasible") is True
                    and r.get("supervision_ok") is True
                    and r.get("permission_status") in {"permission_ok", "sim_no_clinical_permission_required"}
                )
                if secure:
                    secured.add(r["activity"])
                else:
                    at_risk_holds.append({
                        "opportunity": r["opportunity"],
                        "activity": r["activity"],
                        "mode": r["mode"],
                        "schedule_reason": r.get("schedule_reason"),
                        "supervision_reason": r.get("supervision_reason"),
                        "permission_status": r.get("permission_status"),
                        "time_state": r.get("time_state"),
                    })

            done = min(required, len(completed_recognized))
            held = min(max(0, required - done), len(secured))
            remaining = max(0, required - done - held)

            ward_losses = [
                r for r in rows
                if r.get("compensation_eligible") and not r.get("completed")
            ]
            mixed_losses = [
                r for r in rows
                if r.get("compensation_route") == "coordinator_review_mixed_cause"
            ]
            no_shows = [r for r in rows if r.get("loss_reason") == "student_confirmed_absent"]
            unknowns = [
                r for r in rows
                if not r.get("completed") and r.get("loss_source") == "undetermined"
            ]
            sim_issue = bool(completed_unrecognized_sim)

            if remaining == 0:
                route = "fulfilled_or_secured"
            elif at_risk_holds:
                route = "protected_hold_requires_swap"
            elif ward_losses or sim_issue:
                route = "priority_compensation"
            elif no_shows:
                route = "student_application"
            elif unknowns:
                route = "evidence_review"
            else:
                route = "standard_provision"

            for gap_index in range(1, remaining + 1):
                needs.append({
                    "need_id": f"N-{sid}-{scenario}-{gap_index}",
                    "student": sid,
                    "course": course,
                    "original_rotation": student["rotation"],
                    "scenario": scenario,
                    "obligation_order": scenario_index,
                    "gap_index": gap_index,
                    "required": required,
                    "simulation_allowed": sim_allowed,
                    "deadline": student["deadline"],
                    "apply_order": student["apply_order"],
                    "remaining": remaining,
                    "route": route,
                    "compensation_eligible": route == "priority_compensation",
                    "compensation_review_required": bool(mixed_losses),
                    "mixed_loss_basis": [
                        {
                            "record": f"{r['student']}/{r['opportunity']}",
                            "receipt": r.get("receipt_id"),
                            "primary": f"{r.get('loss_source')}/{r.get('loss_reason')}",
                            "factors": r.get("factors", []),
                        }
                        for r in mixed_losses
                    ],
                    "ward_loss_basis": [
                        {
                            "record": f"{r['student']}/{r['opportunity']}",
                            "receipt": r.get("receipt_id"),
                            "source": r.get("loss_source"),
                            "reason": r.get("loss_reason"),
                        }
                        for r in ward_losses
                    ],
                    "no_show_basis": [
                        {"opportunity": r["opportunity"], "receipt": r.get("receipt_id")}
                        for r in no_shows
                    ],
                    "unknown_basis": [
                        {"opportunity": r["opportunity"], "reason": r.get("loss_reason")}
                        for r in unknowns
                    ],
                    "unrecognized_sim": completed_unrecognized_sim,
                    "at_risk_holds": at_risk_holds if gap_index == 1 else [],
                    "secured_activities": sorted(secured),
                    "completed_activities": sorted(completed_recognized),
                })
    return needs
