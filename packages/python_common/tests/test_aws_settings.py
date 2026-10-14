import pytest
from pydantic import ValidationError

from telelink_common.aws import client_options
from telelink_common.settings import ServiceSettings


def test_sdk_settings_allow_emulator_endpoint_only_locally():
    local = ServiceSettings(
        _env_file=None,
        environment="local",
        aws_endpoint_url="http://floci:4566/",
        event_bus_name="telelink-local",
    )
    assert client_options(local) == {
        "region_name": "ap-southeast-1",
        "endpoint_url": "http://floci:4566",
    }
    deployed = ServiceSettings(_env_file=None, environment="development", aws_region="us-east-1")
    assert client_options(deployed) == {"region_name": "us-east-1"}
    for values in (
        {"environment": "production", "aws_endpoint_url": "http://localhost:4566"},
        {"environment": "local", "aws_endpoint_url": "https://events.example.com"},
        {"environment": "local", "aws_endpoint_url": "http://user:pw@localhost:4566"},
        {"environment": "local", "aws_endpoint_url": "http://localhost:4566/path"},
        {"aws_region": "Singapore"},
        {"event_bus_name": "bad bus"},
    ):
        with pytest.raises(ValidationError):
            ServiceSettings(_env_file=None, **values)
