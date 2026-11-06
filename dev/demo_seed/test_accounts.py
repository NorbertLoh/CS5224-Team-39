"""Local-target guards for the accounts-only maintenance command."""

import unittest
from unittest.mock import patch

from accounts import local_settings, patient_phone


class LocalSettingsTests(unittest.TestCase):
    def test_phone_from_ignored_configuration(self):
        with patch.dict("os.environ", {}, clear=True):
            with patch(
                "accounts.dotenv_values", return_value={"LOCAL_SEED_PATIENT_PHONE": "8123 4567"}
            ):
                self.assertEqual(patient_phone(), "+6581234567")

    def test_phone_environment_override(self):
        with patch.dict("os.environ", {"LOCAL_SEED_PATIENT_PHONE": "+65 9123 4567"}):
            with patch(
                "accounts.dotenv_values", return_value={"LOCAL_SEED_PATIENT_PHONE": "81234567"}
            ):
                self.assertEqual(patient_phone(), "+6591234567")

    def test_missing_or_invalid_phone_rejected(self):
        for value in ["", "+12025550100", "12345678"]:
            with self.subTest(value=value), patch.dict("os.environ", {}, clear=True):
                with patch(
                    "accounts.dotenv_values", return_value={"LOCAL_SEED_PATIENT_PHONE": value}
                ):
                    with self.assertRaises(ValueError):
                        patient_phone()

    def settings(self, **changes):
        return {
            "SERVICE_ENVIRONMENT": "local",
            "SERVICE_AWS_ENDPOINT_URL": "http://floci:4566",
            "SERVICE_DATABASE_URL": "postgresql+psycopg://identity:local@postgres:5432/telelink",
            **changes,
        }

    def test_accepts_compose_database(self):
        with patch("accounts.dotenv_values", return_value=self.settings()):
            _, url = local_settings()
        self.assertEqual(url, "postgresql://identity:local@postgres:5432/telelink")

    def test_rejects_unsafe_targets(self):
        cases = [
            {"SERVICE_ENVIRONMENT": "demo"},
            {"SERVICE_AWS_ENDPOINT_URL": "https://cognito-idp.ap-southeast-1.amazonaws.com"},
            {"SERVICE_DATABASE_URL": "postgresql://identity:local@remote/telelink"},
            {"SERVICE_DATABASE_URL": "postgresql://postgres:local@postgres/telelink"},
            {"SERVICE_DATABASE_URL": "postgresql://identity:local@postgres/other"},
            {"SERVICE_DATABASE_URL": "postgresql://identity:local@postgres/telelink?host=remote"},
        ]
        for changes in cases:
            with self.subTest(changes=changes):
                with patch("accounts.dotenv_values", return_value=self.settings(**changes)):
                    with self.assertRaises(ValueError):
                        local_settings()


if __name__ == "__main__":
    unittest.main()
