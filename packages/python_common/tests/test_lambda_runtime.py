import json
import os
import sys
from types import SimpleNamespace

import pytest
from event_fixtures import FIXTURES, sqs_body
from sqlalchemy import create_engine, select
from test_inbox import Store

from telelink_common.lambda_runtime import consume_records, database_sessions, load_settings


@pytest.fixture
def store(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'lambda.db'}")
    yield Store(engine)
    engine.dispose()


def records(*bodies):
    return {"Records": [{"messageId": str(i), "body": body} for i, body in enumerate(bodies)]}


def consume(store, event, handler=None, remaining=120_000):
    context = SimpleNamespace(get_remaining_time_in_millis=lambda: remaining)
    return consume_records(
        event, context, store.sessions, store.inbox, "scheduling", handler or store.record
    )


def test_duplicate_is_acknowledged_only_after_durable_commit(store):
    event = records(sqs_body(FIXTURES[0]))
    assert consume(store, event) == {"batchItemFailures": []}
    # A fresh session sees both the effect and inbox before success was returned.
    assert store.count(store.inbox) == store.count(store.effects) == 1
    assert consume(store, event) == {"batchItemFailures": []}
    assert store.count(store.effects) == 1


def test_failed_handler_rolls_back_and_message_can_retry(store):
    event = records(sqs_body(FIXTURES[0]))

    def fail(session, workflow):
        store.record(session, workflow)
        raise RuntimeError("Do not log private payload text")

    assert consume(store, event, fail) == {"batchItemFailures": [{"itemIdentifier": "0"}]}
    assert store.count(store.inbox) == store.count(store.effects) == 0
    assert consume(store, event) == {"batchItemFailures": []}


def test_invalid_sibling_does_not_retry_committed_message(store):
    event = records("not JSON", sqs_body(FIXTURES[0]))
    assert consume(store, event) == {"batchItemFailures": [{"itemIdentifier": "0"}]}
    assert store.count(store.effects) == 1


def test_near_timeout_leaves_messages_unhandled(store):
    assert consume(store, records(sqs_body(FIXTURES[0])), remaining=9000) == {
        "batchItemFailures": [{"itemIdentifier": "0"}]
    }
    assert store.count(store.inbox) == 0


def test_secrets_loaded_without_changing_process_environment(monkeypatch):
    class Client:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def get_secret_value(self, SecretId):
            assert SecretId == "test-secret"
            return {"SecretString": json.dumps({"database_url": "private-value"})}

    monkeypatch.setenv("SERVICE_CONFIG_SECRET_ARN", "test-secret")
    monkeypatch.delenv("SERVICE_DATABASE_URL", raising=False)
    monkeypatch.setitem(sys.modules, "boto3", SimpleNamespace(client=lambda name: Client()))
    settings = load_settings(lambda **kwargs: SimpleNamespace(log_level="INFO", **kwargs))
    assert settings.database_url == "private-value"
    assert "SERVICE_DATABASE_URL" not in os.environ


def test_database_connections_are_not_retained_between_invocations():
    from sqlalchemy.pool import NullPool

    settings = SimpleNamespace(database_url=None, database_timeout_seconds=3)
    engines = []

    def create(url, **kwargs):
        assert kwargs["poolclass"] is NullPool
        engine = create_engine("sqlite://", poolclass=kwargs["poolclass"])
        engines.append(engine)
        return engine

    with database_sessions(settings, create) as sessions, sessions() as session:
        assert session.scalar(select(1)) == 1
    assert engines[0].pool.status() == "NullPool"
