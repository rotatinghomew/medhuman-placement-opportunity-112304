"""机会核算与整轮补学工具的行为测试。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from clerkship.accounting import account  # noqa: E402
from clerkship.gaps import build_needs  # noqa: E402
from clerkship.pipeline import compare_drafts, run_pipeline  # noqa: E402

DATA = ROOT / "data"


class SampleRoundTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = run_pipeline(DATA)
        cls.acc = cls.result["accounting"]
        cls.plan = cls.result["plan"]
        cls.records = {(r["student"], r["opportunity"]): r for r in cls.acc["records"]}

    def test_three_accounting_calibers_and_key_facts(self):
        s1 = self.records[("S1", "O1")]
        self.assertTrue(s1["planned_attendable"])
        self.assertTrue(s1["actual_attendable"])
        self.assertTrue(s1["completed"])

        s2 = self.records[("S2", "O1")]
        self.assertFalse(s2["schedule_feasible"])
        self.assertEqual(s2["loss_reason"], "consent_withdrawn")
        self.assertNotEqual(s2["loss_reason"], "student_confirmed_absent")

        s6 = self.records[("S6", "O4")]
        self.assertEqual(s6["receipt_status"], "no_show")
        self.assertFalse(s6["compensation_eligible"])
        self.assertEqual(s6["compensation_route"], "student_application")

        for sid in ("S3", "S4"):
            row = self.records[(sid, "O3")]
            self.assertFalse(row["supervision_ok"])
            self.assertEqual(row["loss_source"], "supervision")

    def test_baseline_global_assignments(self):
        got = {(a["student"], a["opportunity"]) for a in self.plan["assignments"]}
        self.assertIn(("S1", "O6"), got)
        self.assertIn(("S2", "O7"), got)
        self.assertIn(("S3", "O10"), got)
        self.assertIn(("S4", "O8"), got)
        self.assertEqual(len(got), 4)

        unresolved = {(u["student"], u["scenario"]) for u in self.plan["unresolved"]}
        self.assertIn(("S5", "listen"), unresolved)
        self.assertIn(("S6", "listen"), unresolved)
        self.assertIn(("S4", "listen"), unresolved)

    def test_swap_consultations_protected_and_consented_preview(self):
        swaps = {(p["student"], p["from_opportunity"], p["to_opportunity"]): p
                 for p in self.plan["swap_consultations"]}
        self.assertIn(("S4", "O6", "O10"), swaps)
        self.assertIn(("S6", "O9", "O8"), swaps)
        s4_swap = swaps[("S4", "O6", "O10")]
        self.assertTrue(s4_swap["old_seat_stays_protected_until_consent"])

        preview = self.plan["combined_preview_if_consents"]
        self.assertTrue(preview["consents"])
        pairs = {(a["student"], a["opportunity"]) for a in preview["assignments"]}
        self.assertIn(("S4", "O10"), pairs)
        self.assertIn(("S6", "O8"), pairs)
        self.assertIn(("S2", "O6"), pairs)
        self.assertIn(("S2", "O9"), pairs)

    def test_late_receipt_reverses_cancellation(self):
        changes = compare_drafts(DATA, 4830, 6950)["changes"]
        s5 = next(c for c in changes if c.get("student") == "S5" and c.get("opportunity") == "O5")
        self.assertFalse(s5["old_completed"])
        self.assertTrue(s5["new_completed"])
        self.assertIn("activity_cancelled", s5["old_loss"])
        self.assertEqual(s5["new_loss"], "none/completed")


class SyntheticRuleTest(unittest.TestCase):
    def _bundle(self, students, opportunities, *, busy=None, announcements=None,
                receipts=None, permissions=None, obligations=None, capacity=1):
        return {
            "student": students,
            "obligation": obligations or [
                {"course": "C", "scenario": "listen", "required": 1, "simulation_allowed": True}
            ],
            "travel": [{"origin": "H", "destination": "L", "minutes": 0}],
            "busy": busy or [],
            "supervisor": [
                {"teacher": "T", "scenario": "listen", "mode": "real", "start_day": 1, "end_day": 9},
                {"teacher": "T", "scenario": "explain", "mode": "real", "start_day": 1, "end_day": 9},
            ],
            "opportunity": opportunities,
            "announcement": announcements or [],
            "permission": permissions if permissions is not None else [
                {"activity": f"E{i}", "restricted_mode": "real", "allowed": 2,
                 "valid_from": 0, "received_at": 0}
                for i in range(10)
            ],
            "receipt": receipts or [],
        }

    def test_two_observers_capacity_two_both_complete(self):
        opp = {"id": "O1", "activity": "E1", "rotation": "R", "day": 1,
               "begin": 600, "end": 660, "place": "L", "scenario": "listen",
               "mode": "real", "teachers": ["T"], "capacity": 2}
        students = [
            {"id": "A", "course": "C", "rotation": "R", "home": "H", "apply_order": 1, "deadline": 2},
            {"id": "B", "course": "C", "rotation": "R", "home": "H", "apply_order": 2, "deadline": 2},
        ]
        anns = [
            {"student": "A", "opportunity": "O1", "sent_at": 0, "status": "notified"},
            {"student": "B", "opportunity": "O1", "sent_at": 0, "status": "notified"},
        ]
        receipts = [
            {"id": "X1", "student": "A", "opportunity": "O1", "status": "present",
             "received_at": 2000, "supersedes": None},
            {"id": "X2", "student": "B", "opportunity": "O1", "status": "present",
             "received_at": 2001, "supersedes": None},
        ]
        b = self._bundle(students, [opp], announcements=anns, receipts=receipts)
        acc = account(b, now=3000)
        self.assertEqual(sum(r["completed"] for r in acc["records"]), 2)
        self.assertEqual(len({c["activity"] for c in acc["event_claims"] if c["completed"]}), 1)

    def test_missing_receipt_is_not_absence(self):
        opp = {"id": "O1", "activity": "E1", "rotation": "R", "day": 1,
               "begin": 600, "end": 660, "place": "L", "scenario": "listen",
               "mode": "real", "teachers": ["T"], "capacity": 1}
        students = [{"id": "A", "course": "C", "rotation": "R", "home": "H",
                     "apply_order": 1, "deadline": 2}]
        anns = [{"student": "A", "opportunity": "O1", "sent_at": 0, "status": "notified"}]
        b = self._bundle(students, [opp], announcements=anns)
        acc = account(b, now=3000)
        row = acc["records"][0]
        self.assertIsNone(row["actual_attendable"])
        self.assertEqual(row["loss_reason"], "final_receipt_missing")
        self.assertNotEqual(row["loss_reason"], "student_confirmed_absent")

    def test_simulation_is_excluded_when_course_does_not_recognize_it(self):
        opp = {"id": "OS", "activity": "ES", "rotation": "R", "day": 2,
               "begin": 600, "end": 660, "place": "L", "scenario": "explain",
               "mode": "sim", "teachers": ["T"], "capacity": 2}
        students = [{"id": "A", "course": "C1", "rotation": "R", "home": "H",
                     "apply_order": 1, "deadline": 3}]
        obligations = [{"course": "C1", "scenario": "explain", "required": 1,
                        "simulation_allowed": False}]
        b = self._bundle(students, [opp], obligations=obligations, permissions=[])
        b["supervisor"].append({"teacher": "T", "scenario": "explain", "mode": "sim",
                                "start_day": 1, "end_day": 9})
        acc = account(b, now=0)
        needs = build_needs(acc, b)
        plan = plan_remediation_simple(acc, needs, b)
        self.assertEqual(plan["assignments"], [])
        self.assertTrue(any(u["scenario"] == "explain" for u in plan["unresolved"]))

    def test_one_option_student_beats_earlier_applicant_with_two_slots(self):
        def opp(oid, day):
            return {"id": oid, "activity": "E" + oid, "rotation": "R", "day": day,
                    "begin": 600, "end": 660, "place": "L", "scenario": "listen",
                    "mode": "real", "teachers": ["T"], "capacity": 1}

        students = [
            {"id": "A", "course": "C", "rotation": "R", "home": "H", "apply_order": 2, "deadline": 2},
            {"id": "B", "course": "C", "rotation": "R", "home": "H", "apply_order": 1, "deadline": 2},
        ]
        # A is busy during Y, leaving X as its only qualified slot.
        busy = [{"student": "A", "day": 2, "begin": 590, "end": 670, "location": "L"}]
        b = self._bundle(
            students, [opp("X", 1), opp("Y", 2)], busy=busy,
            permissions=[
                {"activity": "EX", "restricted_mode": "real", "allowed": 1, "valid_from": 0, "received_at": 0},
                {"activity": "EY", "restricted_mode": "real", "allowed": 1, "valid_from": 0, "received_at": 0},
            ],
        )
        acc = account(b, now=0)
        needs = build_needs(acc, b)
        plan = plan_remediation_simple(acc, needs, b)
        pairs = {(a["student"], a["opportunity"]) for a in plan["assignments"]}
        self.assertEqual(pairs, {("A", "X"), ("B", "Y")})


def plan_remediation_simple(acc, needs, bundle):
    from clerkship.planning import plan_remediation
    return plan_remediation(acc, needs, bundle)


if __name__ == "__main__":
    unittest.main()
