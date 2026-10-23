"""Check representative business-field coverage and linked local examples."""

import json
from datetime import datetime, timedelta, timezone

from dataset import ident
from dotenv import dotenv_values
from psycopg import sql


def finish(ctx):
    ROOT, STATE, admin = ctx.root, ctx.state, ctx.admin
    manifest = json.loads((STATE / "manifest.json").read_text())
    settings = dotenv_values(ROOT / "services/fulfilment/.env")
    if settings.get("SERVICE_DELIVERY_LOCATIONS_PATH"):
        path = ctx.local_file(settings["SERVICE_DELIVERY_LOCATIONS_PATH"])
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        origin = next(iter(data["origins"].values()))
        data["origins"] = {cl["tenant_id"]: origin for cl in manifest["clinics"][:2]}
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    now = datetime.now(timezone.utc)
    patient = next(a for a in manifest["accounts"] if a["email"] == "patient@example.test")
    with admin() as c:
        for status, error in [
            ("failed", "ses_rejected"),
            ("uncertain", "ses_unconfirmed"),
        ]:
            c.execute(
                (
                    "INSERT INTO notification.jobs "
                    "(job_id,tenant_id,event_id,recipient_id,recipient_email,template,"
                    "status,attempts,error_code,send_started_at)"
                    " VALUES (%s,%s,%s,%s,%s,'delivery_updated',%s,1,%s,%s) ON CONFLICT DO "
                    "NOTHING"
                ),
                (
                    ident("notification:" + status),
                    manifest["clinics"][0]["tenant_id"],
                    ident("notification-event:" + status),
                    patient["subject_id"],
                    patient["email"],
                    status,
                    error,
                    now - timedelta(minutes=1),
                ),
            )
        business = {
            "identity": ["subjects", "memberships"],
            "tenant": ["clinics", "audit_events"],
            "scheduling": ["availability_slots", "appointments"],
            "consultation": ["sessions"],
            "clinical_records": [
                "notes",
                "prescriptions",
                "prescription_items",
                "medical_certificates",
            ],
            "billing": ["payments"],
            "fulfilment": [
                "catalogue_items",
                "orders",
                "order_items",
                "quotes",
                "deliveries",
            ],
            "document": ["documents"],
            "notification": ["jobs"],
        }
        coverage = {}
        missing = []
        for schema, tables in business.items():
            for table in tables:
                columns = c.execute(
                    (
                        "SELECT column_name FROM information_schema.columns WHERE "
                        "table_schema=%s AND table_name=%s ORDER BY ordinal_position"
                    ),
                    (schema, table),
                ).fetchall()
                counts = {}
                for (column,) in columns:
                    count = c.execute(
                        sql.SQL("SELECT count(*) FROM {}.{} WHERE {} IS NOT NULL").format(
                            sql.Identifier(schema),
                            sql.Identifier(table),
                            sql.Identifier(column),
                        )
                    ).fetchone()[0]
                    counts[column] = count
                    if count == 0:
                        missing.append(f"{schema}.{table}.{column}")
                coverage[f"{schema}.{table}"] = counts
        assert not missing, f"Business fields with no sample: {missing}"
        for schema, table in [
            ("scheduling", "appointments"),
            ("consultation", "sessions"),
            ("clinical_records", "notes"),
            ("clinical_records", "prescriptions"),
            ("billing", "payments"),
            ("fulfilment", "orders"),
            ("document", "documents"),
        ]:
            for col, target, pk in [
                ("tenant_id", "tenant.clinics", "tenant_id"),
                ("patient_id", "identity.subjects", "subject_id"),
            ]:
                count = c.execute(
                    sql.SQL(
                        "SELECT count(*) FROM {}.{} s LEFT JOIN {} t ON s.{}=t.{} WHERE t.{} IS"
                        " NULL"
                    ).format(
                        sql.Identifier(schema),
                        sql.Identifier(table),
                        sql.SQL(target),
                        sql.Identifier(col),
                        sql.Identifier(pk),
                        sql.Identifier(pk),
                    )
                ).fetchone()[0]
                assert count == 0, (schema, table, col)
        assert (
            c.execute(
                "SELECT count(*) FROM fulfilment.orders WHERE status='paid' AND "
                "payment_status='succeeded' AND medicine_status='ready' AND delivery_id"
                " IS NULL"
            ).fetchone()[0]
            == 0
        )
        assert (
            c.execute(
                "SELECT count(*) FROM fulfilment.deliveries WHERE status='pending' OR "
                "(status IN ('submitted','picked_up','unknown') AND next_poll_at <= "
                "now())"
            ).fetchone()[0]
            == 0
        )
    (STATE / "field-coverage.json").write_text(json.dumps(coverage, indent=2), encoding="utf-8")
    lines = [
        "# Clean local demo dataset",
        "",
        f"Generated: {manifest['generated_at']}",
        "",
        (
            "All records are synthetic. Payment/delivery states are simulated; no "
            "Stripe or courier request was made."
        ),
        "",
        f"Backup: {manifest['backup']}",
        "",
        (
            "Every column in the 19 user-facing business tables below has at least "
            "one non-null example. Mutually exclusive fields are populated across "
            "different valid records; migration, transient admission, inbox/outbox "
            "and idempotency tables are not fabricated."
        ),
        "",
        "| Table | Fields covered |",
        "| --- | --- |",
    ]
    lines += [f"| {table} | {len(cols)}/{len(cols)} |" for table, cols in coverage.items()]
    lines += [
        "",
        "## Login accounts",
        "",
        "Password for every account: `LocalDemo123!`",
        "",
    ]
    lines += [f"- `{a['email']}` — {a['name']}" for a in manifest["accounts"]]
    lines += [
        "",
        "## Demo coverage",
        "",
        (
            "- Two active clinics with logos, descriptions, prices and commissions;"
            " one pending, rejected and suspended clinic."
        ),
        (
            "- Active and revoked memberships; two patients, two doctors, clinic "
            "administrators and a platform administrator."
        ),
        (
            "- Open/withdrawn availability; held, pending, confirmed, ongoing, "
            "completed, expired, cancelled and no-show appointments."
        ),
        (
            "- Notes, draft/issued prescriptions, two medicine items per "
            "prescription, and selected/non-selected medical certificates."
        ),
        (
            "- Consultation and medicine/delivery payments, all six payment "
            "statuses and commission breakdowns."
        ),
        (
            "- Unpaid, preparation, in-transit, delivered, failed, cancelled and "
            "uncertain order examples for each active clinic."
        ),
        (
            "- 42 ready PDFs: prescriptions, consultation receipts, "
            "medication/delivery receipts and MCs; each marked DEMO."
        ),
        "- Local email capture plus sent, failed and uncertain notification examples.",
        "",
        "No new production integration is implied by these database-backed sample states.",
    ]
    (STATE / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(
        f"Validated {len(coverage)} business tables: every field has at least one sample, "
        "all clinic/patient links resolve, and no synthetic courier request is queued."
    )
