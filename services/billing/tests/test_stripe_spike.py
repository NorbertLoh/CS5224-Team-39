"""Provider boundary checks; these fixtures do not establish Stripe feasibility."""

import os
import unittest
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from scripts.stripe_spike import (
    SpikeError,
    StripeTestClient,
    checkout_fields,
    demo,
    inspect_payment,
    load_config,
    verify_evidence,
)


def objects():
    base = {"livemode": False, "currency": "sgd"}
    return [
        base
        | {
            "id": "cs_test_example",
            "metadata": {"task": "X03"},
            "status": "complete",
            "payment_status": "paid",
            "payment_intent": "pi_example",
            "amount_total": 5000,
        },
        base
        | {
            "id": "pi_example",
            "status": "succeeded",
            "latest_charge": "ch_example",
            "amount": 5000,
            "application_fee_amount": 500,
            "transfer_data": {"destination": "acct_example"},
        },
        base
        | {
            "id": "ch_example",
            "paid": True,
            "captured": True,
            "refunded": False,
            "amount_refunded": 0,
            "payment_intent": "pi_example",
            "amount": 5000,
            "application_fee": "fee_example",
            "transfer": "tr_example",
        },
        base
        | {
            "id": "fee_example",
            "charge": "ch_example",
            "amount": 500,
            "account": "acct_example",
            "refunded": False,
            "amount_refunded": 0,
        },
        base
        | {
            "id": "tr_example",
            "source_transaction": "ch_example",
            "amount": 5000,
            "destination": "acct_example",
            "amount_reversed": 0,
        },
    ]


class StripeSpikeTests(unittest.TestCase):
    def test_live_and_missing_keys_refused_before_network(self):
        for key in ("", "sk_live_secret", "rk_live_secret", "pk_test_public"):
            with self.subTest(key=key), self.assertRaises(SpikeError):
                StripeTestClient(key)

    def test_config_reads_only_allowlisted_names_without_evaluation(self):
        with TemporaryDirectory() as folder, patch.dict(os.environ, {}, clear=True):
            path = Path(folder) / ".env"
            path.write_text(
                "STRIPE_SECRET_KEY='sk_test_local'\nOTHER=private\n"
                "STRIPE_CONNECTED_ACCOUNT_ID=acct_example\n",
                encoding="utf-8",
            )
            self.assertEqual(
                load_config(path),
                {
                    "STRIPE_SECRET_KEY": "sk_test_local",
                    "STRIPE_CONNECTED_ACCOUNT_ID": "acct_example",
                },
            )
            with patch.dict(os.environ, {"STRIPE_SECRET_KEY": "sk_test_override"}):
                self.assertEqual(load_config(path)["STRIPE_SECRET_KEY"], "sk_test_override")

    def test_destination_fee_is_on_payment_intent(self):
        fields = checkout_fields("acct_example", "attempt1")
        self.assertEqual(fields["payment_intent_data[application_fee_amount]"], 500)
        self.assertEqual(fields["payment_intent_data[transfer_data][destination]"], "acct_example")
        self.assertEqual(fields["line_items[0][price_data][unit_amount]"], 5000)

    def test_successful_evidence_reports_gross_split(self):
        evidence = verify_evidence(*objects(), "acct_example")
        self.assertEqual(evidence["clinic_gross_minor"], 4500)
        self.assertEqual(evidence["application_fee_minor"], 500)

    def test_unpaid_live_wrong_amount_destination_and_linkage_refused(self):
        changes = (
            [
                (0, "payment_status", "unpaid"),
                (0, "status", "open"),
                (0, "metadata", {}),
                (0, "amount_total", 1),
                (1, "status", "processing"),
                (1, "application_fee_amount", 1),
                (1, "latest_charge", "ch_unrelated"),
                (2, "captured", False),
                (2, "amount_refunded", 1),
                (3, "amount", 1),
                (3, "refunded", True),
                (3, "charge", "ch_unrelated"),
                (4, "destination", "acct_other"),
                (4, "amount_reversed", 1),
                (4, "source_transaction", "ch_other"),
            ]
            + [(i, "livemode", True) for i in range(5)]
            + [(i, "currency", "usd") for i in range(5)]
        )
        for index, key, value in changes:
            with self.subTest(index=index, key=key):
                data = deepcopy(objects())
                data[index][key] = value
                with self.assertRaises(SpikeError):
                    verify_evidence(*data, "acct_example")

    def test_inspection_fetches_independent_objects(self):
        data = objects()

        class FakeClient:
            def request(self, path):
                return dict(
                    zip(
                        (
                            "checkout/sessions/cs_test_example",
                            "payment_intents/pi_example",
                            "charges/ch_example",
                            "application_fees/fee_example",
                            "transfers/tr_example",
                        ),
                        data,
                    )
                )[path]

        result = inspect_payment(FakeClient(), "cs_test_example", "acct_example")
        self.assertTrue(result["provider_verified"])

    def test_demo_cannot_be_mistaken_for_provider_evidence(self):
        result = demo()
        self.assertFalse(result["provider_verified"])
        self.assertFalse(result["task_complete"])
        self.assertEqual(result["mode"], "demo-fixture")


if __name__ == "__main__":
    unittest.main()
