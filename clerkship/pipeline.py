"""一键重算入口。"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .accounting import account, default_as_of
from .gaps import build_needs
from .io import load_bundle
from .planning import plan_remediation


def run_pipeline(root: str | Path, as_of: int | None = None, *, now: int | None = None, consents=None) -> dict[str, Any]:
    bundle = load_bundle(root)
    accounting = account(bundle, as_of=as_of, now=now)
    needs = build_needs(accounting, bundle)
    plan = plan_remediation(accounting, needs, bundle, consents=consents)
    if consents is None:
        recommended_consents = [
            {"student": p["student"], "from": p["from_opportunity"], "to": p["to_opportunity"]}
            for p in plan["swap_consultations"] if p.get("recommended")
        ]
        if recommended_consents:
            combined = plan_remediation(accounting, needs, bundle, consents=recommended_consents)
            plan["recommended_consent_requests"] = recommended_consents
            plan["combined_preview_if_consents"] = {
                "consents": recommended_consents,
                "assignments": combined["assignments"],
                "unresolved": combined["unresolved"],
                "consent_errors": combined["consent_errors"],
            }
    return {
        "root": str(root),
        "evidence_as_of": as_of,
        "now": accounting["now"],
        "bundle": bundle,
        "accounting": accounting,
        "needs": needs,
        "plan": plan,
    }


def compare_drafts(root: str | Path, old_as_of: int, new_as_of: int | None = None) -> dict[str, Any]:
    """比较两个证据时点，展示新回执撤销/确认了什么。"""
    bundle = load_bundle(root)
    new_as_of = default_as_of(bundle) if new_as_of is None else new_as_of
    old = account(bundle, old_as_of)
    new = account(bundle, new_as_of)
    old_by_key = {(r["student"], r["opportunity"]): r for r in old["records"] if not r.get("data_error")}
    new_by_key = {(r["student"], r["opportunity"]): r for r in new["records"] if not r.get("data_error")}
    changes = []
    for key, new_r in sorted(new_by_key.items()):
        old_r = old_by_key.get(key)
        if old_r is None:
            changes.append({"key": key, "change": "new_announcement_or_evidence_window"})
            continue
        if (old_r["loss_source"], old_r["loss_reason"], old_r["completed"], old_r.get("receipt_status")) != (
            new_r["loss_source"], new_r["loss_reason"], new_r["completed"], new_r.get("receipt_status")
        ):
            changes.append({
                "student": key[0],
                "opportunity": key[1],
                "old_receipt_status": old_r.get("receipt_status"),
                "new_receipt_status": new_r.get("receipt_status"),
                "old_loss": f"{old_r['loss_source']}/{old_r['loss_reason']}",
                "new_loss": f"{new_r['loss_source']}/{new_r['loss_reason']}",
                "old_completed": old_r["completed"],
                "new_completed": new_r["completed"],
            })
    return {"old_as_of": old_as_of, "new_as_of": new_as_of, "changes": changes, "old": old, "new": new}
