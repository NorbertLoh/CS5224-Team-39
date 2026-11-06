"""Local-target guards for the accounts-only maintenance command."""

import unittest
from unittest.mock import patch

from accounts import local_settings


class LocalSettingsTests(unittest.TestCase):
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
