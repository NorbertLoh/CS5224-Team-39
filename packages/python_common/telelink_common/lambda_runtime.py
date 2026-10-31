"""Small Lambda adapters; domain decisions remain in the owning service."""

import json
import logging
import os
from contextlib import contextmanager

from sqlalchemy.pool import NullPool

from telelink_common.events import parse_sqs_body
from telelink_common.inbox import handle_event
from telelink_common.logging import configure_logging

logger = logging.getLogger("telelink.lambda")


def load_settings(settings_type):
    """Read service secrets at invocation time without storing them in Terraform state.

    The JSON secret uses Settings field names (database_url, records_secret, ...).
    Explicit secret values override public SERVICE_* environment settings.
    """
    configure_logging("INFO")
    secret_arn = os.environ.get("SERVICE_CONFIG_SECRET_ARN")
    values = {}
    if secret_arn:
        import boto3

        with boto3.client("secretsmanager") as client:
            values = json.loads(client.get_secret_value(SecretId=secret_arn)["SecretString"])
        if not isinstance(values, dict):
            raise ValueError("Service configuration secret must be a JSON object")
    settings = settings_type(_env_file=None, **values)
    configure_logging(settings.log_level)
    for name in ("botocore", "boto3", "httpx", "httpcore", "urllib3"):
        logging.getLogger(name).setLevel(logging.WARNING)
    return settings


@contextmanager
def database_sessions(settings, create_engine):
    """No retained idle pool across frozen Lambda environments."""
    from sqlalchemy.orm import sessionmaker

    engine = create_engine(
        settings.database_url.get_secret_value() if settings.database_url else None,
        timeout_seconds=settings.database_timeout_seconds,
        poolclass=NullPool,
    )
    try:
        yield sessionmaker(engine, expire_on_commit=False)
    finally:
        engine.dispose()


def consume_records(event, context, sessions, inbox, consumer, handler):
    """Return partial failures; Lambda acknowledges only committed inbox transactions.

    Standard queues only. Stop starting jobs near timeout; defer untouched records.
    Do not log bodies, credentials or provider exception messages.
    """
    failures = []
    for record in event["Records"]:
        message_id = record["messageId"]
        if context.get_remaining_time_in_millis() < 10_000:
            failures.append({"itemIdentifier": message_id})
            continue
        try:
            workflow = parse_sqs_body(record["body"], consumer=consumer)
            handle_event(sessions, inbox, consumer, workflow, handler)
        except Exception:
            logger.warning("lambda_record_failed", exc_info=True)
            failures.append({"itemIdentifier": message_id})
    return {"batchItemFailures": failures}
