"""Signing configuration must preserve public host and restrict emulator overrides."""

from unittest.mock import patch

import pytest
from pydantic import ValidationError

from app.downloads import create_signer
from app.settings import Settings


@pytest.mark.parametrize(
    "changes",
    [
        {"cursor_secret": "short"},
        {"download_ttl_seconds": 301},
        {"download_ttl_seconds": 29},
        {"scheduling_url": "https://user:pass@example.test"},
        {"environment": "production", "scheduling_url": "http://example.test"},
        {"s3_browser_endpoint_url": "http://localhost:4566"},
        {"aws_endpoint_url": "http://floci:4566", "s3_browser_endpoint_url": "http://floci:4566"},
        {
            "aws_endpoint_url": "http://localhost:4566",
            "s3_browser_endpoint_url": "https://evil.test",
        },
        {"environment": "production", "s3_browser_endpoint_url": "http://localhost:4566"},
    ],
)
def test_invalid_configuration(changes):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **changes)


def test_signer_requires_browser_host_for_container_emulator():
    settings = Settings(_env_file=None, aws_endpoint_url="http://floci:4566")
    with pytest.raises(ValueError, match="SERVICE_S3_BROWSER_ENDPOINT_URL"):
        create_signer(settings)


def test_aws_signer_uses_aws_endpoint_and_sigv4():
    settings = Settings(_env_file=None, environment="production")
    with patch("app.downloads.boto3.client") as client:
        create_signer(settings)
    options = client.call_args.kwargs
    assert "endpoint_url" not in options
    assert options["config"].signature_version == "s3v4"
