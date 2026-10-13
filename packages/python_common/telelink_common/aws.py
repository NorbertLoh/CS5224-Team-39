"""AWS SDK client construction from shared settings; boto3 is the optional `aws` extra."""

from telelink_common.settings import ServiceSettings


def client_options(settings: ServiceSettings) -> dict:
    """Region plus the local emulator endpoint, when configured.

    Credentials are never passed explicitly: local runs use dummy AWS_* variables
    and AWS deployments use the task role through the default provider chain.
    """
    options = {"region_name": settings.aws_region}
    if settings.aws_endpoint_url:
        options["endpoint_url"] = settings.aws_endpoint_url
    return options


def create_client(service_name: str, settings: ServiceSettings):
    try:
        import boto3
        from botocore.config import Config
    except ImportError:
        raise RuntimeError("AWS clients require the telelink-python-common[aws] extra") from None
    config = Config(
        connect_timeout=3,
        read_timeout=10,
        retries={"mode": "standard", "max_attempts": 3},
    )
    return boto3.client(service_name, config=config, **client_options(settings))
