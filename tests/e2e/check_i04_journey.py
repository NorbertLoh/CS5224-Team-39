"""Read-only I04 source-event, notification-job and local SES capture checks.

Run with notification's dependencies. No events are published, messages consumed,
emails sent or business rows changed. SES acceptance does not mean inbox delivery.
"""

import argparse
import json
import sys
from contextlib import ExitStack
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID

import httpx
import psycopg
from dotenv import dotenv_values
from psycopg.rows import dict_row
from sqlalchemy.engine import make_url
from telelink_common.events import parse_sqs_body

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "services/notification"))
from app.recipients import RecipientDirectory  # noqa: E402
from app.settings import Settings  # noqa: E402
from app.templates import render_email  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("appointment_id", type=UUID)
    parser.add_argument("document_id", type=UUID)
    parser.add_argument("delivery_id", type=UUID)
    parser.add_argument("--config-root", type=Path, default=ROOT)
    args = parser.parse_args()
    settings = Settings(_env_file=args.config_root / "services/notification/.env")
    if settings.environment not in {"local", "test"} or settings.aws_endpoint_url not in {
        "http://localhost:4566",
        "http://127.0.0.1:4566",
    }:
        parser.error("Only local store-only Floci is supported")
    for service in ("identity", "scheduling", "document", "fulfilment"):
        if urlsplit(getattr(settings, service + "_url") or "").hostname not in {
            "localhost",
            "127.0.0.1",
        }:
            parser.error("Only host-local owner APIs are supported")

    def check(name, passed):
        print(f"{'PASS' if passed else 'FAIL'}  {name}", flush=True)
        if not passed:
            raise AssertionError(name)

    with ExitStack() as stack:

        def database(service):
            values = dotenv_values(args.config_root / f"services/{service}/.env")
            url = make_url(values["SERVICE_DATABASE_URL"])
            if url.host not in {"localhost", "127.0.0.1"} or url.port != 55411:
                parser.error("Use the persistent local database on 55411")
            return stack.enter_context(
                psycopg.connect(
                    url.set(drivername="postgresql").render_as_string(hide_password=False),
                    autocommit=True,
                    options="-c default_transaction_read_only=on",
                    row_factory=dict_row,
                )
            )

        owners = {
            service: database(service) for service in ("scheduling", "document", "fulfilment")
        }
        jobs_db = database("notification")
        directory = RecipientDirectory(settings)
        stack.callback(directory.close)
        http = stack.enter_context(httpx.Client(timeout=15, trust_env=False))
        response = http.get(settings.aws_endpoint_url + "/_aws/ses")
        response.raise_for_status()
        captured = response.json()["messages"]
        delivery = (
            owners["fulfilment"]
            .execute(
                "SELECT o.appointment_id,o.prescription_id,o.patient_id,o.tenant_id,d.status "
                "FROM fulfilment.orders o JOIN fulfilment.deliveries d ON d.order_id=o.order_id "
                "WHERE d.delivery_id=%s AND o.delivery_id=d.delivery_id",
                (args.delivery_id,),
            )
            .fetchone()
        )
        check(
            "delivery belongs to this consultation",
            delivery is not None and delivery["appointment_id"] == args.appointment_id,
        )
        acceptance_ids = []
        cases = (
            (
                "scheduling",
                "appointment_confirmed.v1",
                "appointment_id",
                args.appointment_id,
                "booking_confirmed",
            ),
            ("document", "document_ready.v1", "document_id", args.document_id, "document_ready"),
            (
                "fulfilment",
                "delivery_status_changed.v1",
                "delivery_id",
                args.delivery_id,
                "delivery_updated",
            ),
        )
        for service, kind, field, resource_id, template in cases:
            rows = (
                owners[service]
                .execute(
                    f"SELECT source,detail_type,detail,published_at FROM {service}.event_outbox "
                    "WHERE detail_type=%s AND detail::jsonb->'data'->>%s=%s",
                    (kind, field, str(resource_id)),
                )
                .fetchall()
            )
            if service == "fulfilment":
                rows = [
                    row
                    for row in rows
                    if json.loads(row["detail"])["data"]["status"] == delivery["status"]
                ]
            check(
                f"{template}: one published owner event",
                len(rows) == 1 and rows[0]["published_at"] is not None,
            )
            row = rows[0]
            event = parse_sqs_body(
                json.dumps(
                    {
                        "source": row["source"],
                        "detail-type": row["detail_type"],
                        "detail": json.loads(row["detail"]),
                    }
                ),
                consumer="notification",
            )
            check(
                f"{template}: source links match the journey",
                event.tenant_id == delivery["tenant_id"]
                and (
                    service != "document"
                    or (
                        event.data.appointment_id == args.appointment_id
                        and event.data.prescription_id == delivery["prescription_id"]
                    )
                ),
            )
            recipient = directory.resolve(event)
            check(
                f"{template}: authoritative synthetic patient",
                recipient is not None
                and recipient.subject_id == delivery["patient_id"]
                and recipient.email.endswith(("@example.test", "@telelink.test")),
            )
            jobs = jobs_db.execute(
                "SELECT * FROM notification.jobs WHERE event_id=%s",
                (event.event_id,),
            ).fetchall()
            inbox = jobs_db.execute(
                "SELECT count(*) AS count FROM notification.event_inbox "
                "WHERE consumer='notification' AND event_id=%s",
                (event.event_id,),
            ).fetchone()["count"]
            check(f"{template}: one committed job and inbox receipt", len(jobs) == inbox == 1)
            job = jobs[0]
            check(
                f"{template}: accepted once for the correct patient",
                job["template"] == template
                and job["tenant_id"] == event.tenant_id
                and job["recipient_id"] == recipient.subject_id
                and job["recipient_email"] == recipient.email
                and job["status"] == "sent"
                and job["attempts"] == 1
                and job["sent_at"] is not None
                and bool(job["provider_message_id"])
                and job["error_code"] is None,
            )
            messages = [item for item in captured if item.get("Id") == job["provider_message_id"]]
            expected = render_email(template, settings.app_url)
            check(
                f"{template}: exact generic SES capture",
                len(messages) == 1
                and messages[0].get("Source") == settings.email_sender
                and messages[0].get("Destination", {}).get("ToAddresses") == [recipient.email]
                and not messages[0].get("Destination", {}).get("CcAddresses")
                and not messages[0].get("Destination", {}).get("BccAddresses")
                and messages[0].get("Subject") == expected.subject
                and messages[0].get("Body", {}).get("text_part") == expected.text
                and messages[0].get("Body", {}).get("html_part") == expected.html,
            )
            acceptance_ids.append(job["provider_message_id"])
        check("three distinct SES acceptance IDs", len(set(acceptance_ids)) == 3)
        print("I04 persisted-state/capture checks passed.")
        print("Actual transport steps: docs/I04-local-journey.md")


if __name__ == "__main__":
    main()
