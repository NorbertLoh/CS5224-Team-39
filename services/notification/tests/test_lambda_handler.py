from contextlib import contextmanager
from types import SimpleNamespace

from app import lambda_handler


def setup_dispatch(monkeypatch, remaining=120_000):
    calls = []
    monkeypatch.setattr(lambda_handler, "load_settings", lambda _: object())

    @contextmanager
    def sessions(*args):
        yield object()

    monkeypatch.setattr(lambda_handler, "database_sessions", sessions)
    sender = SimpleNamespace(client=SimpleNamespace(close=lambda: calls.append("closed")))
    monkeypatch.setattr(lambda_handler, "SESEmailSender", lambda _: sender)
    monkeypatch.setattr(lambda_handler, "recover_stale", lambda *args: calls.append("recovered"))
    context = SimpleNamespace(get_remaining_time_in_millis=lambda: remaining)
    return calls, context


def test_schedule_drains_durable_jobs_without_new_sqs_events(monkeypatch):
    calls, context = setup_dispatch(monkeypatch)
    available = iter([True, True, False])
    monkeypatch.setattr(lambda_handler, "dispatch_one", lambda *args: next(available))
    assert lambda_handler.dispatch({}, context) == {"dispatched": 2}
    assert calls == ["recovered", "closed"]


def test_schedule_has_a_hard_job_limit(monkeypatch):
    calls, context = setup_dispatch(monkeypatch)
    monkeypatch.setattr(lambda_handler, "dispatch_one", lambda *args: True)
    assert lambda_handler.dispatch({}, context) == {"dispatched": 20}
    assert calls[-1] == "closed"


def test_schedule_stops_before_starting_send_near_timeout(monkeypatch):
    calls, context = setup_dispatch(monkeypatch, remaining=14_000)

    def unexpected(*args):
        raise AssertionError("Must not send near timeout")

    monkeypatch.setattr(lambda_handler, "dispatch_one", unexpected)
    assert lambda_handler.dispatch({}, context) == {"dispatched": 0}
    assert calls == ["recovered", "closed"]
