"""SQS-triggered PDF generation; the HTTP API and outbox publisher stay separate."""

from contextlib import ExitStack

from telelink_common.aws import create_client
from telelink_common.lambda_runtime import consume_records, database_sessions, load_settings

from app.database import create_database_engine
from app.integrations.records import RecordsClient
from app.integrations.storage import PrivatePDFStore
from app.models import event_inbox
from app.services.generation import GeneratePrescription
from app.services.mc_generation import GenerateMedicalCertificate
from app.settings import Settings


def handler(event, context):
    settings = load_settings(Settings)
    with ExitStack() as stack:
        sessions = stack.enter_context(database_sessions(settings, create_database_engine))
        records = RecordsClient(settings)
        stack.callback(records.close)
        s3 = create_client("s3", settings)
        stack.callback(s3.close)
        store = PrivatePDFStore(s3, settings.document_bucket)
        store.verify_private()
        prescriptions = GeneratePrescription(records, store)
        certificates = GenerateMedicalCertificate(records, store)

        def generate(session, workflow):
            if workflow.detail_type == "medical_certificate_issued.v1":
                certificates(session, workflow)
            else:
                prescriptions(session, workflow)

        return consume_records(event, context, sessions, event_inbox, "document", generate)
