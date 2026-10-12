"""Focused integrity regressions for the shared fixture dataset."""

import copy
import json
import unittest
from pathlib import Path

from validate import InvalidFixture, validate


class FixtureIntegrityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.baseline = json.loads(
            Path(__file__).with_name("telelink.json").read_text(encoding="utf-8")
        )

    def setUp(self):
        self.data = copy.deepcopy(self.baseline)

    def test_canonical_dataset_is_valid(self):
        validate(self.data)

    def test_cross_clinic_appointment_is_rejected(self):
        self.data["appointments"][0]["tenant_id"] = self.data["clinics"][1]["tenant_id"]
        with self.assertRaisesRegex(InvalidFixture, "Mismatched tenant_id"):
            validate(self.data)

    def test_two_live_reservations_for_same_slot_are_rejected(self):
        held = copy.deepcopy(next(a for a in self.data["appointments"] if a["status"] == "held"))
        held["appointment_id"] = "00000000-0000-4000-8000-000000009999"
        self.data["appointments"].append(held)
        with self.assertRaisesRegex(InvalidFixture, "Double-booked slot"):
            validate(self.data)

    def test_order_quantity_tampering_is_rejected(self):
        self.data["orders"][0]["items"][0]["quantity"] += 1
        with self.assertRaisesRegex(InvalidFixture, "Mismatched quantity"):
            validate(self.data)

    def test_delivery_without_readiness_is_rejected(self):
        self.data["orders"][0]["medicine_status"] = "not_ready"
        with self.assertRaisesRegex(InvalidFixture, "Delivery bypassed paid AND ready"):
            validate(self.data)

    def test_order_quantity_requires_integer_type(self):
        self.data["orders"][0]["items"][0]["quantity"] = 2.0
        with self.assertRaisesRegex(InvalidFixture, "Invalid order quantity"):
            validate(self.data)

    def test_primary_id_cannot_be_null(self):
        self.data["subjects"][0]["subject_id"] = None
        with self.assertRaisesRegex(InvalidFixture, "Null or invalid primary ID"):
            validate(self.data)

    def test_money_float_is_rejected(self):
        self.data["payments"][0]["amount"]["amount_minor"] = 2500.5
        with self.assertRaisesRegex(InvalidFixture, "Invalid SGD money"):
            validate(self.data)

    def test_medication_commission_cannot_include_delivery_fee(self):
        payment = next(p for p in self.data["payments"] if p["purpose"] == "medication_delivery")
        payment["commission_amount"]["amount_minor"] = payment["amount"]["amount_minor"] // 10
        with self.assertRaisesRegex(InvalidFixture, "Wrong commission base"):
            validate(self.data)

    def test_event_amount_mismatch_is_rejected(self):
        event = self.data["events"][0]
        detail = json.loads(event["Detail"])
        detail["data"]["amount"]["amount_minor"] += 1
        event["Detail"] = json.dumps(detail)
        with self.assertRaisesRegex(InvalidFixture, "Mismatched amount"):
            validate(self.data)

    def test_hold_expires_at_exact_deadline(self):
        self.data["as_of"] = "2026-10-13T03:05:00.000Z"
        with self.assertRaisesRegex(InvalidFixture, "Hold status disagrees"):
            validate(self.data)

    def test_clinic_admin_cannot_be_granted_clinical_access(self):
        case = next(c for c in self.data["access_cases"] if c["name"] == "clinic_admin_no_clinical")
        case["expected_allowed"] = True
        case["expected_http_status"] = 200
        with self.assertRaisesRegex(InvalidFixture, "Wrong access expectation"):
            validate(self.data)


if __name__ == "__main__":
    unittest.main()
