"""Run separately from download APIs: python -m app.worker [--once]."""

import argparse

from sqlalchemy.orm import sessionmaker
from telelink_common.aws import create_client
from telelink_common.inbox import consume_batch

from app.database import create_database_engine
from app.generation import GeneratePrescription
from app.mc_generation import GenerateMedicalCertificate
from app.models import event_inbox
from app.records import RecordsClient
from app.settings import Settings
from app.storage import PrivatePDFStore


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    config = Settings()
    engine = create_database_engine(
        config.database_url.get_secret_value() if config.database_url else None
    )
    records = RecordsClient(config)
    sqs, s3 = create_client("sqs", config), create_client("s3", config)
    try:
        store = PrivatePDFStore(s3, config.document_bucket)
        store.verify_private()
        queue_url = sqs.get_queue_url(QueueName=config.document_queue_name)["QueueUrl"]
        sessions = sessionmaker(engine, expire_on_commit=False)
        prescriptions = GeneratePrescription(records, store)
        certificates = GenerateMedicalCertificate(records, store)

        def handler(session, event):
            if event.detail_type == "medical_certificate_issued.v1":
                certificates(session, event)
            else:
                prescriptions(session, event)

        while True:
            result = consume_batch(
                sessions,
                event_inbox,
                sqs,
                queue_url,
                "document",
                handler,
                max_messages=1,
                wait_seconds=0 if args.once else 5,
            )
            if args.once:
                print(
                    f"processed={result.processed} duplicates={result.duplicates} "
                    f"failed={result.failed}"
                )
                return
    finally:
        records.close()
        sqs.close()
        s3.close()
        engine.dispose()


if __name__ == "__main__":
    main()
