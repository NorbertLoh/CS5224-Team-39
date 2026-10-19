from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from io import BytesIO
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pypdf import PdfReader
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker
from telelink_common.events import new_event
from telelink_common.inbox.consumer import handle_event
from test_persistence import database as database
from test_worker import MemoryS3

from app.mc_generation import GenerateMedicalCertificate, IssuedMC, document_id_for
from app.models import Document, event_inbox, event_outbox
from app.storage import PrivatePDFStore


@pytest.fixture
def mc(database):
    event = new_event(
        "medical_certificate_issued.v1",
        tenant_id=uuid4(),
        correlation_id=uuid4(),
        occurred_at=datetime.now(timezone.utc),
        data={
            "medical_certificate_id": uuid4(),
            "appointment_id": uuid4(),
            "patient_id": uuid4(),
            "doctor_id": uuid4(),
        },
    )
    source = IssuedMC(
        **event.data.model_dump(),
        tenant_id=event.tenant_id,
        selected=True,
        issued_at=datetime.now(timezone.utc),
        finalized_at=datetime.now(timezone.utc),
        consultation_date="2026-10-19",
        start_date="2026-10-31",
        end_date="2026-11-01",
        duration_days=2,
        additional_notes="Rest & recover <safely>",
        clinic_name="Synthetic Clinic",
        patient_name="Synthetic Patient",
        doctor_name="Synthetic Doctor",
    )
    state = {"fail": False, "calls": 0}

    def fetch(event):
        state["calls"] += 1
        if state["fail"]:
            raise ValueError("private clinical source must not leak")
        return source

    s3 = MemoryS3()
    return SimpleNamespace(
        event=event,
        source=source,
        state=state,
        s3=s3,
        engine=database,
        sessions=sessionmaker(database),
        handler=GenerateMedicalCertificate(
            SimpleNamespace(medical_certificate=fetch), PrivatePDFStore(s3, "private")
        ),
    )


def run(mc, event=None):
    return handle_event(mc.sessions, event_inbox, "document", event or mc.event, mc.handler)


def read(mc):
    with Session(mc.engine) as session:
        return session.get(Document, document_id_for(mc.event.data.medical_certificate_id))


def test_mc_pdf_contents_and_duplicate_event_recovery(mc):
    assert run(mc)
    assert not run(mc)
    assert run(mc, mc.event.model_copy(update={"event_id": uuid4()}))
    assert mc.s3.puts == 1 and mc.state["calls"] == 1
    assert read(mc).status == "ready"
    text = "\n".join(
        page.extract_text()
        for page in PdfReader(BytesIO(next(iter(mc.s3.objects.values()))["Body"])).pages
    )
    for expected in (
        "Synthetic Patient",
        "Synthetic Doctor",
        "Synthetic Clinic",
        "31 Oct 2026",
        "01 Nov 2026",
        "2 day(s)",
        "Rest & recover <safely>",
    ):
        assert expected in text
    with Session(mc.engine) as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(event_outbox)
                .where(event_outbox.c.detail.contains(str(mc.event.tenant_id)))
            )
            == 1
        )


@pytest.mark.parametrize("failure", ["source", "upload", "unknown-upload"])
def test_failed_status_is_durable_and_replay_reuses_object(mc, failure):
    mc.state["fail"] = failure == "source"
    mc.s3.fail_put = failure == "upload"
    mc.s3.unknown_put = failure == "unknown-upload"
    with pytest.raises(RuntimeError, match="Medical certificate PDF processing failed"):
        run(mc)
    assert read(mc).status == "failed"
    mc.state["fail"] = mc.s3.fail_put = mc.s3.unknown_put = False
    assert run(mc)
    assert read(mc).status == "ready" and mc.s3.puts == 1


def test_concurrent_distinct_events_create_one_pdf(mc):
    events = [mc.event.model_copy(update={"event_id": uuid4()}) for _ in range(4)]
    with ThreadPoolExecutor(4) as pool:
        assert all(pool.map(lambda event: run(mc, event), events))
    assert mc.s3.puts == 1 and mc.state["calls"] == 1


def test_uploaded_mc_survives_commit_failure_without_duplicate_pdf(mc):
    from sqlalchemy import event

    def fail_commit(session):
        raise RuntimeError("synthetic commit failure")

    event.listen(mc.sessions, "before_commit", fail_commit)
    try:
        with pytest.raises(RuntimeError):
            run(mc)
    finally:
        event.remove(mc.sessions, "before_commit", fail_commit)
    assert read(mc).status == "pending"
    assert run(mc)
    assert read(mc).status == "ready" and mc.s3.puts == 1 and mc.state["calls"] == 1
