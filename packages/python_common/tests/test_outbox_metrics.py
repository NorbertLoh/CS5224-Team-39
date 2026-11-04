import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from telelink_common.outbox import metrics


def test_backlog_includes_retry_delayed_events_and_emits_zero(monkeypatch, capsys):
    monkeypatch.setenv("SERVICE_OUTBOX_METRICS", "true")
    monkeypatch.setenv("SERVICE_ENVIRONMENT", "demo")
    monkeypatch.setattr(metrics, "_last_emitted", {})
    now = datetime.now(timezone.utc)
    rows = iter([(2, now - timedelta(seconds=400), now), (0, None, now)])
    statements = []

    def execute(statement):
        statements.append(str(statement))
        return SimpleNamespace(one=lambda: next(rows))

    from sqlalchemy import MetaData

    from telelink_common.outbox import outbox_table

    table = outbox_table(MetaData(schema="billing"))
    session = SimpleNamespace(execute=execute)
    ticks = iter([0, 1, 61])
    monkeypatch.setattr(metrics.time, "monotonic", lambda: next(ticks))
    metrics.emit_backlog(session, table)
    metrics.emit_backlog(session, table)  # Throttled, no database query.
    metrics.emit_backlog(session, table)
    first, second = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert first["PendingEvents"] == 2 and first["OldestPendingAge"] == 400
    assert first["Service"] == "billing" and first["Environment"] == "demo"
    assert second["PendingEvents"] == second["OldestPendingAge"] == 0
    assert len(statements) == 2
    assert "next_attempt_at" not in statements[0]


def test_metrics_disabled_does_not_query_database(monkeypatch):
    monkeypatch.delenv("SERVICE_OUTBOX_METRICS", raising=False)
    metrics.emit_backlog(None, None)
