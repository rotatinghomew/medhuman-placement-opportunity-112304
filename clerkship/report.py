"""把核算和安排结果写成 JSON/CSV/Markdown。"""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from .pipeline import compare_drafts


def _flatten(record: dict[str, Any]) -> dict[str, Any]:
    flat: dict[str, Any] = {}
    for key, value in record.items():
        if key.startswith("_"):
            continue
        if isinstance(value, (list, dict)):
            flat[key] = json.dumps(value, ensure_ascii=False, sort_keys=True)
        elif value is None or isinstance(value, (str, int, float, bool)):
            flat[key] = value
        else:
            flat[key] = str(value)
    return flat


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    flat_rows = [_flatten(r) for r in rows]
    fields: list[str] = []
    seen: set[str] = set()
    for row in flat_rows:
        for key in row:
            if key not in seen:
                fields.append(key)
                seen.add(key)
    with path.open("w", encoding="utf-8", newline="") as source:
        writer = csv.DictWriter(source, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(flat_rows)


def opportunity_metrics(accounting: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for oid, view in sorted(accounting["opportunity_views"].items()):
        opp = view["opportunity"]
        rows.append({
            "opportunity": oid,
            "activity": opp["activity"],
            "rotation": opp["rotation"],
            "scenario": opp["scenario"],
            "mode": opp["mode"],
            "day": opp["day"],
            "begin": opp["begin"],
            "end": opp["end"],
            "capacity": opp["capacity"],
            "time_state": view["time_state"],
            "supervision_ok": view["supervision"]["ok"],
            "supervision_reason": view["supervision"]["reason"],
            "permission_status": view["permission"]["status"],
            "permission_allowed": view["permission"].get("allowed"),
            "active_count": view["active_count"],
            "protected_count": view["protected_count"],
            "remaining_capacity": view["remaining_capacity"],
            "bookable": view["bookable"],
            "not_bookable_reasons": ";".join(view["not_bookable_reasons"]),
        })
    return rows


def rotation_student_decisions(result: dict[str, Any]) -> list[dict[str, Any]]:
    """完成后按原轮转查询：指标、补学决定和依据的扁平索引。"""
    plan = result["plan"]
    assignments = plan["assignments"]
    unresolved = plan["unresolved"]
    rows: list[dict[str, Any]] = []
    for metric in result["accounting"]["rotation_metrics"]:
        rotation = metric["rotation"]
        rot_assignments = [a for a in assignments if a.get("original_rotation") == rotation]
        rot_protected = [a for a in plan.get("protected_appointments", []) if a.get("original_rotation") == rotation]
        rot_unresolved = [u for u in unresolved if u.get("original_rotation") == rotation]
        rows.append({
            "original_rotation": rotation,
            "planned_bookings": metric["planned_bookings"],
            "planned_attendable": metric["planned_attendable"],
            "actual_attendable": metric["actual_attendable"],
            "completed": metric["completed"],
            "actual_unknown_past": metric["actual_unknown_past"],
            "loss_supervision": metric["loss_supervision"],
            "loss_activity": metric["loss_activity"],
            "loss_student": metric["loss_student"],
            "loss_undetermined": metric["loss_undetermined"],
            "proposed_assignments": len(rot_assignments),
            "protected_appointments": len(rot_protected),
            "unresolved_gaps": len(rot_unresolved),
            "assignment_ids": ";".join(a["assignment_id"] for a in rot_assignments),
            "protected_ids": ";".join(a["assignment_id"] for a in rot_protected),
            "unresolved_need_ids": ";".join(u["need_id"] for u in rot_unresolved),
            "basis": json.dumps({
                "metrics": metric,
                "assignments": [
                    {
                        "id": a["assignment_id"],
                        "student": a["student"],
                        "fills": a["gap_description"],
                        "slot": f"{a['opportunity']} day{a['day']} {a['begin']}-{a['end']}",
                        "route": a["route"],
                        "basis": a.get("ward_loss_basis") or a.get("student_application_basis"),
                    }
                    for a in rot_assignments
                ],
                "protected": rot_protected,
                "unresolved": rot_unresolved,
            }, ensure_ascii=False, sort_keys=True),
        })
    return rows


def query_rotation(result: dict[str, Any], rotation: str) -> dict[str, Any]:
    """完成后按原轮转号查询指标、补学决定和依据。"""
    decision = next(
        (row for row in rotation_student_decisions(result) if row["original_rotation"] == rotation),
        None,
    )
    return {
        "rotation": rotation,
        "metrics": next((m for m in result["accounting"]["rotation_metrics"] if m["rotation"] == rotation), None),
        "decision_index": decision,
        "records": [r for r in result["accounting"]["records"] if r.get("original_rotation") == rotation],
        "needs": [n for n in result["needs"] if n.get("original_rotation") == rotation],
        "assignments": [a for a in result["plan"]["assignments"] if a.get("original_rotation") == rotation],
        "protected_appointments": [a for a in result["plan"].get("protected_appointments", []) if a.get("original_rotation") == rotation],
        "unresolved": [u for u in result["plan"]["unresolved"] if u.get("original_rotation") == rotation],
        "swap_consultations": [
            p for p in result["plan"]["swap_consultations"]
            if next((s["rotation"] for s in result["bundle"]["student"] if s["id"] == p["student"]), None) == rotation
        ],
    }


def write_outputs(result: dict[str, Any], out_dir: str | Path) -> None:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    accounting = result["accounting"]
    plan = result["plan"]

    serializable = {
        key: value for key, value in result.items() if key != "bundle"
    }
    (out / "result.json").write_text(
        json.dumps(serializable, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    (out / "metrics.json").write_text(json.dumps({
        "as_of": result.get("evidence_as_of"),
        "now": result.get("now"),
        "rotation_metrics": accounting["rotation_metrics"],
        "opportunity_metrics": opportunity_metrics(accounting),
        "event_claims": accounting["event_claims"],
        "activity_audit": accounting.get("activity_audit", []),
    }, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    (out / "plan.json").write_text(
        json.dumps(plan, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    write_csv(out / "opportunity_accounting.csv", accounting["records"])
    write_csv(out / "event_claims.csv", accounting["event_claims"])
    write_csv(out / "activity_audit.csv", accounting.get("activity_audit", []))
    write_csv(out / "rotation_metrics.csv", accounting["rotation_metrics"])
    write_csv(out / "opportunity_metrics.csv", opportunity_metrics(accounting))
    write_csv(out / "student_gaps.csv", result["needs"])
    write_csv(out / "remediation_assignments.csv", plan["assignments"])
    write_csv(out / "protected_appointments.csv", plan.get("protected_appointments", []))
    write_csv(out / "unresolved_gaps.csv", plan["unresolved"])
    write_csv(out / "swap_consultations.csv", plan["swap_consultations"])
    write_csv(out / "release_consultations.csv", plan.get("release_consultations", []))
    write_csv(out / "do_not_send.csv", plan["do_not_send"])
    write_csv(out / "rotation_decisions.csv", rotation_student_decisions(result))
    (out / "report.md").write_text(render_markdown(result), encoding="utf-8")


def _table(rows: list[dict[str, Any]], columns: list[tuple[str, str]]) -> str:
    if not rows:
        return "（无）\n"
    head = "| " + " | ".join(label for _, label in columns) + " |"
    sep = "| " + " | ".join("---" for _ in columns) + " |"
    lines = [head, sep]
    for row in rows:
        values = []
        for key, _ in columns:
            value = row.get(key, "")
            if isinstance(value, (list, dict)):
                value = json.dumps(value, ensure_ascii=False)
            if value is None:
                value = ""
            values.append(str(value).replace("|", "\\|").replace("\n", " "))
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines) + "\n"


def render_markdown(result: dict[str, Any]) -> str:
    acc = result["accounting"]
    plan = result["plan"]
    lines: list[str] = []
    lines.append("# 见习机会核算与补学复核报告\n")
    lines.append(f"- 证据时点：{result.get('evidence_as_of') or '资料包全部证据'}")
    lines.append(f"- 协调员复核时点：绝对分钟 {result['now']}（日×1440+分钟）")
    lines.append("- 区间口径：时间区间左闭右开；同一活动号不重复计完成；未出现最终回执不记缺席。\n")

    lines.append("## 一、按原轮转的三种口径与损失来源\n")
    metric_rows = []
    for m in acc["rotation_metrics"]:
        metric_rows.append({
            "rotation": m["rotation"],
            "bookings": m["planned_bookings"],
            "planned": m["planned_attendable"],
            "actual": m["actual_attendable"],
            "completed": m["completed"],
            "unknown": m["actual_unknown_past"],
            "supervision": m["loss_supervision"],
            "activity": m["loss_activity"],
            "student": m["loss_student"],
            "undetermined": m["loss_undetermined"],
        })
    lines.append(_table(metric_rows, [
        ("rotation", "原轮转"), ("bookings", "通知预约"),
        ("planned", "原计划可参加"), ("actual", "当天实际可参加"), ("completed", "实际完成"),
        ("unknown", "已过时段但回执未定"), ("supervision", "带教不足"),
        ("activity", "活动/同意/许可"), ("student", "学生侧"),
        ("undetermined", "资料无法确定"),
    ]))

    lines.append("\n## 二、学生-机会明细与依据\n")
    detail_rows = [{
        "student": r["student"], "opp": r["opportunity"], "activity": r["activity"],
        "scenario": f"{r['course']}/{r['scenario']}/{r['mode']}",
        "receipt": r.get("receipt_status") or "",
        "actual": "" if r["actual_attendable"] is None else ("是" if r["actual_attendable"] else "否"),
        "done": "是" if r["completed"] else "否",
        "source": r["loss_source_zh"], "reason": r["loss_reason_zh"],
        "schedule": r["schedule_reason"], "permission": r["permission_status"],
        "route": r["compensation_route"],
    } for r in acc["records"] if not r.get("data_error")]
    lines.append(_table(detail_rows, [
        ("student", "学生"), ("opp", "机会"), ("activity", "临床活动号"),
        ("scenario", "课程/场景/方式"), ("receipt", "最新回执"),
        ("actual", "实际可参加"), ("done", "完成"), ("source", "损失来源"),
        ("reason", "主原因"), ("schedule", "路程时间"), ("permission", "许可"),
        ("route", "处理路径"),
    ]))

    lines.append("\n## 三、本轮基线补学安排（尚未代发通知）\n")
    protected = plan.get("protected_appointments", [])
    if protected:
        lines.append("### 已接受、受保护的现有预约\n")
        lines.append(_table(protected, [
            ("student", "学生"), ("original_rotation", "原轮转"), ("gap_description", "缺口"),
            ("opportunity", "机会"), ("day", "日"), ("begin", "开始"), ("end", "结束"),
            ("mode", "方式"), ("performable_with_current_data", "当前资料下可履行"),
            ("schedule_reason", "时间依据"), ("permission_status", "许可"),
        ]))
    lines.append("\n### 新生成的待复核安排\n")
    assign_rows = [{
        "id": a["assignment_id"], "student": a["student"], "rotation": a["original_rotation"],
        "gap": a["gap_description"], "opp": a["opportunity"],
        "time": f"day{a['day']} {a['begin']}-{a['end']}",
        "mode": a["mode"], "deadline": a["deadline_day"], "route": a["route"],
    } for a in plan["assignments"] if a.get("status") != "consented_swap_confirmed"]
    lines.append(_table(assign_rows, [
        ("id", "安排号"), ("student", "学生"), ("rotation", "原轮转"),
        ("gap", "补回缺口"), ("opp", "机会"), ("time", "时间"),
        ("mode", "方式"), ("deadline", "截止日"), ("route", "路径"),
    ]))

    consented = [a for a in plan["assignments"] if a.get("status") == "consented_swap_confirmed"]
    if consented:
        lines.append("\n### 已确认的一次性换约\n")
        lines.append(_table([{
            "student": a["student"], "gap": a["gap_description"], "opp": a["opportunity"],
            "time": f"day{a['day']} {a['begin']}-{a['end']}", "id": a["assignment_id"],
        } for a in consented], [
            ("student", "学生"), ("gap", "缺口"), ("opp", "新预约"), ("time", "时间"), ("id", "安排号")
        ]))

    lines.append("\n## 四、截止前仍无法补足的缺口与原因\n")
    lines.append(_table(plan["unresolved"], [
        ("need_id", "缺口"), ("student", "学生"), ("original_rotation", "原轮转"),
        ("scenario", "场景"), ("deadline", "截止日"), ("route", "路径"),
        ("primary_reason_zh", "主要原因"), ("blocking_reason_counts", "全部限制计数"),
    ]))

    lines.append("\n## 五、可征询的一次性换约（同意前旧位不释放）\n")
    swap_rows = [{
        "student": p["student"], "from": p["from_opportunity"], "to": p["to_opportunity"],
        "fills": p["fills"], "preferred": "是" if p.get("recommended") else "备选",
        "risk": "是" if p["old_hold_at_risk"] else "",
        "new": f"day{p['new_slot']['day']} {p['new_slot']['begin']}-{p['new_slot']['end']} {p['new_slot']['mode']}",
        "goes": json.dumps(p.get("released_old_slot_would_go_to", []), ensure_ascii=False),
        "tradeoff": json.dumps(p.get("tradeoff_vs_baseline", {}), ensure_ascii=False),
    } for p in plan["swap_consultations"]]
    lines.append(_table(swap_rows, [
        ("student", "学生"), ("from", "旧约"), ("to", "建议新约"), ("fills", "补回缺口"),
        ("preferred", "建议度"), ("risk", "旧约有风险"), ("new", "新时段"),
        ("goes", "若同意旧位可安排"), ("tradeoff", "相对基线的得失"),
    ]))

    releases = plan.get("release_consultations", [])
    if releases:
        lines.append("\n### 新证据后已多余但不能自动释放的预约\n")
        lines.append(_table(releases, [
            ("student", "学生"), ("opportunity", "预约"), ("fills", "场景"),
            ("consult_type", "征询类型"), ("status", "状态"), ("basis", "依据"),
        ]))

    preview = plan.get("combined_preview_if_consents")
    if preview:
        lines.append("\n### 若所有首选换约均获同意的整轮预览\n")
        lines.append("征询清单：`" + json.dumps(preview["consents"], ensure_ascii=False) + "`\n")
        lines.append(_table([{
            "student": a["student"], "gap": a["gap_description"], "opp": a["opportunity"],
            "time": f"day{a['day']} {a['begin']}-{a['end']}", "status": a["status"],
        } for a in preview["assignments"]], [
            ("student", "学生"), ("gap", "缺口"), ("opp", "机会"), ("time", "时间"), ("status", "状态")
        ]))
        lines.append("仍未补足：" + ", ".join(u["need_id"] for u in preview["unresolved"]) + "\n")

    lines.append("\n## 六、不应再发/需保护的安排\n")
    lines.append(_table(plan["do_not_send"], [
        ("student", "学生"), ("opportunity", "机会"), ("scope", "场景"),
        ("code", "类别"), ("detail", "依据"),
    ]))

    if result.get("draft_changes"):
        draft = result["draft_changes"]
        lines.append("\n## 七、新证据到达后的草案重算\n")
        lines.append(f"- 旧时点：{draft['old_as_of']}；新时点：{draft['new_as_of']}")
        lines.append(_table(draft["changes"], [
            ("student", "学生"), ("opportunity", "机会"),
            ("old_receipt_status", "旧回执"), ("new_receipt_status", "新回执"),
            ("old_loss", "旧损失口径"), ("new_loss", "新损失口径"),
            ("old_completed", "旧完成"), ("new_completed", "新完成"),
            ("change", "变化"), ("key", "键"),
        ]))

    lines.append("\n## 八、课程要求缺口原始汇总\n")
    lines.append(_table(result["needs"], [
        ("need_id", "缺口"), ("student", "学生"), ("route", "路径"),
        ("deadline", "截止日"), ("simulation_allowed", "承认模拟"),
        ("compensation_eligible", "优先补偿资格"),
        ("compensation_review_required", "混合原因待复核"),
        ("ward_loss_basis", "院方损失依据"),
        ("no_show_basis", "缺席申请依据"), ("unknown_basis", "待证依据"),
    ]))
    return "\n".join(lines) + "\n"


def write_draft_comparison(root: str | Path, old_as_of: int, new_as_of: int | None, out_dir: Path) -> dict[str, Any]:
    changes = compare_drafts(root, old_as_of, new_as_of)
    path = out_dir / "draft_changes.json"
    slim = {k: v for k, v in changes.items() if k not in {"old", "new"}}
    path.write_text(json.dumps(slim, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    write_csv(out_dir / "draft_changes.csv", slim["changes"])
    return slim
