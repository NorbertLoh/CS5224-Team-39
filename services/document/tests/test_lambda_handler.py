from contextlib import contextmanager
from types import SimpleNamespace

from app import lambda_handler


def test_lambda_routes_existing_document_types_and_releases_clients(monkeypatch):
    calls = []
    settings = SimpleNamespace(document_bucket="private-test-bucket")
    monkeypatch.setattr(lambda_handler, "load_settings", lambda _: settings)

    @contextmanager
    def sessions(*args):
        yield "sessions"
        calls.append("database-closed")

    monkeypatch.setattr(lambda_handler, "database_sessions", sessions)
    records = SimpleNamespace(close=lambda: calls.append("records-closed"))
    s3 = SimpleNamespace(close=lambda: calls.append("s3-closed"))
    monkeypatch.setattr(lambda_handler, "RecordsClient", lambda _: records)
    monkeypatch.setattr(lambda_handler, "create_client", lambda *args: s3)
    monkeypatch.setattr(
        lambda_handler,
        "PrivatePDFStore",
        lambda *args: SimpleNamespace(verify_private=lambda: calls.append("verified")),
    )
    monkeypatch.setattr(
        lambda_handler,
        "GeneratePrescription",
        lambda *args: lambda *args: calls.append("prescription"),
    )
    monkeypatch.setattr(
        lambda_handler, "GenerateMedicalCertificate", lambda *args: lambda *args: calls.append("mc")
    )

    def consume(event, context, sessions, inbox, consumer, generate):
        assert sessions == "sessions" and consumer == "document"
        generate(None, SimpleNamespace(detail_type="prescription_issued.v1"))
        generate(None, SimpleNamespace(detail_type="medical_certificate_issued.v1"))
        return {"batchItemFailures": []}

    monkeypatch.setattr(lambda_handler, "consume_records", consume)
    assert lambda_handler.handler({}, None) == {"batchItemFailures": []}
    assert calls == [
        "verified",
        "prescription",
        "mc",
        "s3-closed",
        "records-closed",
        "database-closed",
    ]
