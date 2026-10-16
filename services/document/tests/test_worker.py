import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from hashlib import sha256
from io import BytesIO
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from botocore.exceptions import ClientError
from pydantic import SecretStr
from pypdf import PdfReader
from sqlalchemy import event as sqlalchemy_event
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker
from telelink_common.events import new_event
from telelink_common.inbox import consume_batch
from telelink_common.inbox.consumer import handle_event
from test_persistence import database as database

from app.generation import GeneratePrescription
from app.models import Document, event_inbox, event_outbox
from app.records import IssuedPrescription, RecordsClient
from app.settings import Settings
from app.storage import PUBLIC_BLOCK, PrivatePDFStore


def workflow(**changes):
    event = new_event(
        "prescription_issued.v1",
        tenant_id=uuid4(),
        correlation_id=uuid4(),
        occurred_at=datetime.now(timezone.utc),
        data={"prescription_id": uuid4(), "appointment_id": uuid4()},
    )
    return event.model_copy(update=changes)


def source_for(event):
    return IssuedPrescription(
        prescription_id=event.data.prescription_id,
        tenant_id=event.tenant_id,
        appointment_id=event.data.appointment_id,
        patient_id=uuid4(),
        doctor_id=uuid4(),
        status="issued",
        issued_at=datetime.now(timezone.utc),
        clinic_name="Synthetic Clinic",
        patient_name="Synthetic Patient",
        doctor_name="Synthetic Doctor",
        items=[
            {
                "prescription_item_id": uuid4(),
                "medication_id": uuid4(),
                "display_name": "Synthetic medication",
                "quantity": 2,
                "instructions": "Synthetic private instructions",
            }
        ],
    )


class MemoryS3:
    def __init__(self):
        self.objects, self.puts = {}, 0
        self.private, self.fail_put, self.unknown_put = True, False, False

    def get_public_access_block(self, **kwargs):
        return {"PublicAccessBlockConfiguration": {key: self.private for key in PUBLIC_BLOCK}}

    def get_object(self, Bucket, Key):
        if Key not in self.objects:
            raise ClientError({"Error": {"Code": "NoSuchKey"}}, "GetObject")
        obj = self.objects[Key]
        return {
            "Body": BytesIO(obj["Body"]),
            "ContentLength": len(obj["Body"]),
            "ContentType": obj["ContentType"],
            "Metadata": obj["Metadata"],
        }

    def put_object(self, **kwargs):
        assert kwargs["IfNoneMatch"] == "*"
        assert kwargs["ServerSideEncryption"] == "AES256"
        assert kwargs["CacheControl"] == "no-store" and "ACL" not in kwargs
        if self.fail_put:
            raise TimeoutError("Synthetic private provider error")
        if kwargs["Key"] in self.objects:
            raise ClientError({"Error": {"Code": "PreconditionFailed"}}, "PutObject")
        self.objects[kwargs["Key"]] = kwargs
        self.puts += 1
        if self.unknown_put:
            self.unknown_put = False
            raise TimeoutError("Upload accepted but response lost")


@pytest.fixture
def job(database):
    event, s3 = workflow(), MemoryS3()
    source = source_for(event)
    state = {"calls": 0, "fail": False}

    def fetch(event):
        state["calls"] += 1
        if state["fail"]:
            raise ValueError("Synthetic private instructions")
        return source

    sessions = sessionmaker(database)
    handler = GeneratePrescription(
        SimpleNamespace(prescription=fetch), PrivatePDFStore(s3, "private")
    )
    return SimpleNamespace(
        event=event,
        s3=s3,
        source=source,
        state=state,
        sessions=sessions,
        handler=handler,
        engine=database,
    )


def run(job, event=None):
    return handle_event(job.sessions, event_inbox, "document", event or job.event, job.handler)


def rows(job):
    with Session(job.engine) as session:
        return session.scalars(
            select(Document).where(Document.prescription_id == job.event.data.prescription_id)
        ).all()


def test_generate_pdf_once_and_commit_ready_inbox_outbox(job):
    assert run(job) is True
    assert run(job) is False
    assert run(job, job.event.model_copy(update={"event_id": uuid4()})) is True
    assert job.s3.puts == 1 and job.state["calls"] == 1
    row = rows(job)[0]
    assert row.status == "ready" and row.patient_id == job.source.patient_id
    obj = job.s3.objects[row.storage_key]
    assert row.sha256 == sha256(obj["Body"]).hexdigest()
    pdf = "".join(page.extract_text() for page in PdfReader(BytesIO(obj["Body"])).pages)
    assert "Synthetic private instructions" in pdf and "Synthetic Doctor" in pdf
    assert "None" not in pdf
    with Session(job.engine) as session:
        ready = session.execute(
            select(event_outbox).where(event_outbox.c.detail.contains(str(row.document_id)))
        ).one()
        assert ready.detail_type == "document_ready.v1"
        assert "instructions" not in ready.detail and "Patient" not in ready.detail


def test_existing_failed_metadata_row_is_reused(job):
    document_id = uuid4()
    with Session(job.engine) as session, session.begin():
        session.add(
            Document(
                document_id=document_id,
                tenant_id=job.event.tenant_id,
                appointment_id=job.event.data.appointment_id,
                prescription_id=job.event.data.prescription_id,
                patient_id=job.source.patient_id,
                doctor_id=job.source.doctor_id,
                kind="prescription_pdf",
                status="failed",
            )
        )
    assert run(job)
    assert rows(job)[0].document_id == document_id and rows(job)[0].status == "ready"


def test_conditional_upload_preserves_the_first_object(job):
    assert run(job)
    key, obj = next(iter(job.s3.objects.items()))
    expected = {
        field: obj["Metadata"][field]
        for field in ("document-id", "prescription-id", "tenant-id", "appointment-id")
    }
    stored = job.handler.store.put(key, b"%PDF-new-content", expected, uuid4(), uuid4())
    assert stored.sha256 == sha256(obj["Body"]).hexdigest()
    assert stored.patient_id == job.source.patient_id and job.s3.puts == 1


def test_wrong_tenant_replay_cannot_reuse_a_ready_document(job):
    assert run(job)
    with pytest.raises(RuntimeError):
        run(job, job.event.model_copy(update={"event_id": uuid4(), "tenant_id": uuid4()}))
    assert len(rows(job)) == 1 and job.s3.puts == 1


def test_parallel_distinct_events_create_one_logical_document(job):
    events = [job.event.model_copy(update={"event_id": uuid4()}) for _ in range(6)]
    with ThreadPoolExecutor(max_workers=6) as pool:
        assert all(pool.map(lambda event: run(job, event), events))
    assert len(rows(job)) == 1 and job.s3.puts == 1 and job.state["calls"] == 1


@pytest.mark.parametrize("failure", ["source", "upload", "unknown-upload", "commit"])
def test_failures_rollback_and_retry_without_replacing_uploaded_pdf(job, failure):
    if failure == "source":
        job.state["fail"] = True
    elif failure == "upload":
        job.s3.fail_put = True
    elif failure == "unknown-upload":
        job.s3.unknown_put = True

    def commit_failure(session):
        raise RuntimeError("Synthetic commit failure")

    if failure == "commit":
        sqlalchemy_event.listen(job.sessions, "before_commit", commit_failure)
    try:
        with pytest.raises(RuntimeError):
            run(job)
    finally:
        if failure == "commit":
            sqlalchemy_event.remove(job.sessions, "before_commit", commit_failure)
    assert rows(job) == []
    with Session(job.engine) as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(event_inbox)
                .where(event_inbox.c.event_id == job.event.event_id)
            )
            == 0
        )
    preserved = next(iter(job.s3.objects.values()))["Body"] if job.s3.objects else None
    job.s3.fail_put = False
    job.state["fail"] = preserved is not None  # Recovery must not fetch changing profiles again.
    assert run(job)
    assert len(rows(job)) == 1 and job.s3.puts == 1
    if preserved:
        assert next(iter(job.s3.objects.values()))["Body"] == preserved


def test_private_bucket_and_existing_object_integrity_fail_closed(job):
    job.s3.private = False
    with pytest.raises(RuntimeError):
        run(job)
    assert job.s3.puts == 0 and rows(job) == []
    job.s3.private = True
    assert run(job)
    key, obj = next(iter(job.s3.objects.items()))
    obj["Metadata"]["sha256"] = "0" * 64
    with pytest.raises(RuntimeError, match="integrity"):
        job.handler.store.load(key, {"tenant-id": str(job.event.tenant_id)})


def test_failure_is_not_acknowledged_and_clinical_text_is_not_logged(job, caplog):
    job.state["fail"] = True
    body = json.dumps(
        {
            "source": job.event.source,
            "detail-type": job.event.detail_type,
            "detail": job.event.detail(),
        }
    )
    deleted = []
    sqs = SimpleNamespace(
        receive_message=lambda **kwargs: {"Messages": [{"Body": body, "ReceiptHandle": "receipt"}]},
        delete_message=lambda **kwargs: deleted.append(kwargs),
    )
    result = consume_batch(
        job.sessions, event_inbox, sqs, "queue", "document", job.handler, wait_seconds=0
    )
    assert result.failed == 1 and not deleted and rows(job) == []
    assert "Synthetic private instructions" not in caplog.text
    job.state["fail"] = False
    assert (
        consume_batch(
            job.sessions, event_inbox, sqs, "queue", "document", job.handler, wait_seconds=0
        ).processed
        == 1
    )
    assert len(deleted) == 1


@pytest.mark.parametrize(
    "mode", ["valid", "tenant", "appointment", "prescription", "draft", "down", "malformed"]
)
def test_records_adapter_checks_authentication_and_context(mode):
    event = workflow()
    data = source_for(event).model_dump(mode="json")
    config = Settings(
        _env_file=None,
        records_url="http://records/api/v1/clinical-records",
        records_secret=SecretStr("records-document-test-key-at-least-32-bytes"),
    )

    def response(request):
        assert request.headers["authorization"].startswith("Bearer ey")
        assert request.url.params["purpose"] == "prescription_pdf"
        assert request.headers["x-request-id"] == str(event.correlation_id)
        if mode in {"tenant", "appointment", "prescription"}:
            data[mode + "_id"] = str(uuid4())
        if mode == "draft":
            data["status"] = "draft"
        if mode == "malformed":
            data["items"] = [{"instructions": "Synthetic private instructions"}]
        return httpx.Response(503 if mode == "down" else 200, json=data)

    client = RecordsClient(config, transport=httpx.MockTransport(response))
    try:
        if mode == "valid":
            assert client.prescription(event).prescription_id == event.data.prescription_id
        else:
            with pytest.raises(RuntimeError, match="lookup failed") as error:
                client.prescription(event)
            assert "Synthetic private instructions" not in str(error.value)
    finally:
        client.close()
