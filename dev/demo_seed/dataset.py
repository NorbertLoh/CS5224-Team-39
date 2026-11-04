"""Synthetic business examples. Called only after an explicit backed-up local reset."""

import hashlib
import io
import json
import subprocess
from datetime import datetime, timedelta, timezone
from uuid import NAMESPACE_URL, uuid5
from zoneinfo import ZoneInfo

import boto3
from dotenv import dotenv_values, set_key
from environment import SCHEMAS
from PIL import Image, ImageDraw
from psycopg import sql
from psycopg.types.json import Jsonb


def ident(name):
    return str(uuid5(NAMESPACE_URL, "telelink:clean-demo-20261023:" + name))


def insert(connection, schema, table, **values):
    query = sql.SQL("INSERT INTO {}.{} ({}) VALUES ({})").format(
        sql.Identifier(schema),
        sql.Identifier(table),
        sql.SQL(",").join(map(sql.Identifier, values)),
        sql.SQL(",").join(sql.Placeholder() for _ in values),
    )
    connection.execute(query, list(values.values()))


def seed(ctx):
    ROOT, STATE, ORIGIN, AWS, admin = (
        ctx.root,
        ctx.state,
        ctx.origin,
        ctx.aws_options,
        ctx.admin,
    )
    now = datetime.now(timezone.utc).replace(microsecond=0)
    day = (
        datetime.now(ZoneInfo("Asia/Singapore"))
        .replace(hour=9, minute=0, second=0, microsecond=0)
        .astimezone(timezone.utc)
    )

    ctx.require_backup()
    backup = ctx.backup

    cognito = boto3.client("cognito-idp", **AWS)
    pools = [
        p
        for p in cognito.list_user_pools(MaxResults=60)["UserPools"]
        if p["Name"] == "telelink-local"
    ]
    if len(pools) != 1 or pools[0]["Id"] != ctx.pool:
        raise ValueError("The preflighted local Cognito pool changed; reset refused.")
    pool = pools[0]["Id"]
    users = []
    for page in cognito.get_paginator("list_users").paginate(UserPoolId=pool):
        users.extend(page["Users"])
    for user in users:
        cognito.admin_delete_user(UserPoolId=pool, Username=user["Username"])
    accounts = [
        ("patient", "Alex Chen (Demo)", ["patient"]),
        ("patient2", "Jamie Lim (Demo)", ["patient"]),
        ("doctor", "Dr Avery Tan (Demo)", []),
        ("doctor2", "Dr Riley Wong (Demo)", []),
        ("clinic", "Morgan Lee (Demo)", []),
        ("clinic2", "Casey Koh (Demo)", []),
        ("staff", "Jordan Goh (Demo)", []),
        ("platform", "Taylor Ong (Demo)", ["platform_admin"]),
    ]
    subjects = {}
    for key, name, roles in accounts:
        email = key + "@example.test"
        cognito.admin_create_user(
            UserPoolId=pool,
            Username=email,
            MessageAction="SUPPRESS",
            TemporaryPassword="LocalDemo123!",
            UserAttributes=[
                {"Name": "email", "Value": email},
                {"Name": "email_verified", "Value": "true"},
                {"Name": "name", "Value": name},
            ],
        )
        cognito.admin_set_user_password(
            UserPoolId=pool, Username=email, Password="LocalDemo123!", Permanent=True
        )
        attrs = {
            a["Name"]: a["Value"]
            for a in cognito.admin_get_user(UserPoolId=pool, Username=email)["UserAttributes"]
        }
        subjects[key] = dict(
            subject_id=ident("subject:" + key),
            cognito_sub=attrs["sub"],
            display_name=name,
            global_roles=roles,
            email=email,
        )
    print(
        f"Recreated {len(accounts)} local demo accounts; "
        "Cognito pool/client and remote callbacks preserved.",
        flush=True,
    )

    s3 = boto3.client("s3", **AWS)
    document_settings = dotenv_values(ROOT / "services/document/.env")
    tenant_settings = dotenv_values(ROOT / "services/tenant/.env")
    doc_bucket = document_settings.get("SERVICE_DOCUMENT_BUCKET", "telelink-local-documents")
    logo_bucket = tenant_settings.get("SERVICE_LOGO_BUCKET", "telelink-local-branding")
    for bucket in [doc_bucket, logo_bucket]:
        if not bucket.startswith("telelink-local-"):
            raise ValueError("Only local demo buckets may be reset")
        for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket):
            for obj in page.get("Contents", []):
                s3.delete_object(Bucket=bucket, Key=obj["Key"])
    sqs = boto3.client("sqs", **AWS)
    queues = sqs.list_queues(QueueNamePrefix="telelink-local-").get("QueueUrls", [])
    for url in queues:
        try:
            sqs.purge_queue(QueueUrl=url)
        except sqs.exceptions.PurgeQueueInProgress:
            pass
    ctx.flush_redis()

    clinics = []
    for i, (slug, name, status, color, fee, rate, reason) in enumerate(
        [
            (
                "local-clinic",
                "Harbour Family Clinic (Demo)",
                "active",
                "#156B63",
                3500,
                1000,
                None,
            ),
            (
                "orchard-demo",
                "Orchard Wellness Clinic (Demo)",
                "active",
                "#4355A5",
                4500,
                1250,
                None,
            ),
            (
                "rivergate-demo",
                "Rivergate Clinic (Demo)",
                "pending_review",
                "#A66B25",
                4000,
                1000,
                None,
            ),
            (
                "meadow-demo",
                "Meadow Clinic (Demo)",
                "rejected",
                "#A53D58",
                3000,
                750,
                "Demo review example: supporting registration information is incomplete.",
            ),
            (
                "hillview-demo",
                "Hillview Clinic (Demo)",
                "suspended",
                "#74519B",
                3800,
                1500,
                "Demo suspension example: updated operating details are required.",
            ),
        ]
    ):
        cid = ident("clinic:" + slug)
        clinics.append(
            dict(
                tenant_id=cid,
                creator_subject_id=subjects["clinic"]["subject_id"],
                membership_provisioned=True,
                slug=slug,
                name=name,
                status=status,
                primary_color=color,
                logo_url=f"{ORIGIN}/api/v1/tenant/clinics/{cid}/public-logo",
                description=(
                    f"{name} is a synthetic TeleLink demonstration clinic. "
                    "Example weekday consultations, follow-up care and medication delivery. "
                    "No real clinical service is provided."
                ),
                consultation_price_minor=fee,
                currency="SGD",
                commission_bps=rate,
                review_reason=reason,
            )
        )

    pdf_jobs = []
    appointment_manifest = []
    order_manifest = []
    with admin() as c:
        tables = c.execute(
            (
                "SELECT schemaname,tablename FROM pg_tables WHERE schemaname=ANY(%s) "
                "AND tablename <> 'alembic_version' ORDER BY schemaname,tablename"
            ),
            (SCHEMAS,),
        ).fetchall()
        c.execute(
            sql.SQL("TRUNCATE {} RESTART IDENTITY CASCADE").format(
                sql.SQL(",").join(
                    sql.SQL("{}.{}").format(sql.Identifier(s), sql.Identifier(t)) for s, t in tables
                )
            )
        )
        for sub in subjects.values():
            insert(c, "identity", "subjects", **sub)
        for clinic in clinics:
            insert(c, "tenant", "clinics", **clinic)
            cid = clinic["tenant_id"]
            insert(
                c,
                "identity",
                "memberships",
                membership_id=ident("membership:clinic:" + cid),
                subject_id=subjects["clinic"]["subject_id"],
                tenant_id=cid,
                roles=["clinic_admin"],
                status="active",
            )
            if clinic["status"] != "pending_review":
                insert(
                    c,
                    "tenant",
                    "audit_events",
                    event_id=ident("review:" + cid),
                    tenant_id=cid,
                    actor_subject_id=subjects["platform"]["subject_id"],
                    action={
                        "active": "clinic.approved",
                        "rejected": "clinic.rejected",
                        "suspended": "clinic.suspended",
                    }[clinic["status"]],
                    previous_values=Jsonb({"status": "pending_review"}),
                    new_values=Jsonb({"status": clinic["status"]}),
                    reason=clinic["review_reason"] or "Synthetic demo clinic approved for preview.",
                )
        for idx, clinic in enumerate(clinics[:2]):
            cid = clinic["tenant_id"]
            doc = subjects["doctor" if idx == 0 else "doctor2"]
            for key, roles, status in [
                ("doctor" if idx == 0 else "doctor2", ["doctor"], "active"),
                ("clinic2", ["clinic_admin"], "active" if idx == 1 else "revoked"),
                ("staff", ["clinic_admin"], "revoked"),
            ]:
                insert(
                    c,
                    "identity",
                    "memberships",
                    membership_id=ident("membership:" + key + ":" + cid),
                    subject_id=subjects[key]["subject_id"],
                    tenant_id=cid,
                    roles=roles,
                    status=status,
                )
            medications = []
            for j, (name, unit, price, active) in enumerate(
                [
                    ("Demo sample tablet A (not for use)", "tablet", 50, True),
                    ("Demo sample solution B (not for use)", "bottle", 800, True),
                    ("Demo retired item (not for use)", "pack", 300, False),
                ]
            ):
                mid = ident(f"medication:{idx}:{j}")
                medications.append((mid, name, unit, price))
                insert(
                    c,
                    "fulfilment",
                    "catalogue_items",
                    tenant_id=cid,
                    medication_id=mid,
                    display_name=name,
                    unit_label=unit,
                    unit_price_minor=price,
                    active=active,
                )
            scenarios = [
                ("delivered", "completed", -7),
                ("preparing", "completed", -6),
                ("unpaid", "completed", -5),
                ("in-transit", "completed", -4),
                ("delivery-failed", "completed", -3),
                ("cancelled-order", "completed", -2),
                ("delivery-uncertain", "completed", -1),
                ("live", "in_progress", 0),
                ("upcoming", "confirmed", 1),
                ("held", "held", 2),
                ("pending-payment", "pending_payment", 3),
                ("cancelled", "cancelled", -8),
                ("expired", "expired", -9),
                ("no-show", "no_show", -10),
                ("refund-pending", "cancelled", -11),
                ("refund-failed", "cancelled", -12),
            ]
            for j, (scenario, status, offset) in enumerate(scenarios):
                prefix = f"{idx}:{scenario}"
                aid = ident("appointment:" + prefix)
                sid = ident("slot:" + prefix)
                start = (
                    now.replace(minute=(now.minute // 30) * 30, second=0)
                    if scenario == "live"
                    else day + timedelta(days=offset, hours=idx)
                )
                end = start + timedelta(minutes=30)
                created = min(now - timedelta(hours=3), start - timedelta(hours=1))
                held = status in ("held", "pending_payment", "expired")
                if status == "expired":
                    created = start - timedelta(hours=1)
                elif held:
                    created = now - timedelta(minutes=1)
                deadline = created + timedelta(minutes=10) if held else None
                patient = subjects["patient"] if j % 4 != 3 else subjects["patient2"]
                pay_status = (
                    "pending"
                    if status in ("held", "pending_payment")
                    else "failed"
                    if status == "expired"
                    else "refunded"
                    if status == "cancelled"
                    else "succeeded"
                )
                if scenario == "refund-pending":
                    pay_status = "refund_pending"
                if scenario == "refund-failed":
                    pay_status = "refund_failed"
                payid = ident("consultation-payment:" + prefix)
                payment_resolution = (
                    "awaiting_payment"
                    if held and status != "expired"
                    else "refunded"
                    if pay_status == "refunded"
                    else "refund_required"
                    if pay_status.startswith("refund_")
                    else "none"
                    if pay_status == "failed"
                    else "confirmed"
                )
                insert(
                    c,
                    "scheduling",
                    "availability_slots",
                    slot_id=sid,
                    tenant_id=cid,
                    doctor_id=doc["subject_id"],
                    starts_at=start,
                    ends_at=end,
                    created_at=created,
                )
                ap = dict(
                    appointment_id=aid,
                    slot_id=sid,
                    tenant_id=cid,
                    doctor_id=doc["subject_id"],
                    patient_id=patient["subject_id"],
                    starts_at=start,
                    ends_at=end,
                    status=status,
                    created_at=created,
                    hold_expires_at=deadline,
                    consultation_price_minor=clinic["consultation_price_minor"],
                    currency="SGD",
                    payment_id=payid,
                    payment_resolution=payment_resolution,
                    patient_name=patient["display_name"],
                    doctor_name=doc["display_name"],
                    clinic_name=clinic["name"],
                )
                if status == "cancelled":
                    ap.update(
                        cancelled_at=start - timedelta(minutes=20),
                        cancelled_by_subject_id=patient["subject_id"],
                        cancellation_reason=(
                            "Synthetic demo cancellation: patient requested a different "
                            "consultation time."
                        ),
                    )
                insert(c, "scheduling", "appointments", **ap)
                appointment_manifest.append(
                    dict(
                        clinic=clinic["name"],
                        scenario=scenario,
                        appointment_id=aid,
                        tenant_id=cid,
                        patient_id=patient["subject_id"],
                    )
                )
                fee = clinic["consultation_price_minor"]
                commission = fee * clinic["commission_bps"] // 10000
                insert(
                    c,
                    "billing",
                    "payments",
                    payment_id=payid,
                    tenant_id=cid,
                    patient_id=patient["subject_id"],
                    purpose="consultation",
                    appointment_id=aid,
                    status=pay_status,
                    resolution="refund_required" if pay_status.startswith("refund_") else "none",
                    amount_minor=fee,
                    currency="SGD",
                    commissionable_minor=fee,
                    delivery_fee_minor=0,
                    commission_bps=clinic["commission_bps"],
                    commission_amount_minor=commission,
                    clinic_amount_minor=fee - commission,
                    provider="demo_seed",
                    provider_account_id="DEMO-NO-CHARGE",
                    provider_checkout_id="DEMO-CHECKOUT-" + payid,
                    provider_payment_id="DEMO-PAYMENT-" + payid,
                    provider_idempotency_key="DEMO-" + payid,
                    created_at=created,
                )
                if status in ("completed", "in_progress", "confirmed"):
                    {
                        "completed": "completed",
                        "in_progress": "in_progress",
                        "confirmed": "scheduled",
                    }[status]
                    sessionid = ident("session:" + prefix)
                    insert(
                        c,
                        "consultation",
                        "sessions",
                        session_id=sessionid,
                        appointment_id=aid,
                        tenant_id=cid,
                        patient_id=patient["subject_id"],
                        doctor_id=doc["subject_id"],
                        starts_at=start,
                        ends_at=end,
                        status="scheduled",
                        started_at=None,
                        ended_at=None,
                        created_at=created,
                    )
                    if status != "confirmed":
                        c.execute(
                            (
                                "UPDATE consultation.sessions "
                                "SET status='in_progress',started_at=%s "
                                "WHERE session_id=%s"
                            ),
                            (start + timedelta(seconds=1), sessionid),
                        )
                    if status == "completed":
                        c.execute(
                            (
                                "UPDATE consultation.sessions "
                                "SET status='completed',ended_at=%s WHERE "
                                "session_id=%s"
                            ),
                            (end, sessionid),
                        )
                if status not in ("completed", "in_progress"):
                    continue
                issued = end if status == "completed" else None
                common = dict(
                    tenant_id=cid,
                    appointment_id=aid,
                    patient_id=patient["subject_id"],
                    doctor_id=doc["subject_id"],
                )
                insert(
                    c,
                    "clinical_records",
                    "notes",
                    note_id=ident("note:" + prefix),
                    **common,
                    text=(
                        f"DEMO DATA ONLY. Example consultation note for {scenario}. "
                        "Presenting concern: demonstration follow-up. History, assessment "
                        "and follow-up are synthetic; this is not medical advice."
                    ),
                    created_at=created,
                )
                rx = ident("prescription:" + prefix)
                insert(
                    c,
                    "clinical_records",
                    "prescriptions",
                    prescription_id=rx,
                    **common,
                    status="issued" if issued else "draft",
                    issued_at=issued,
                    created_at=created,
                )
                for k, (mid, name, unit, price) in enumerate(medications[:2]):
                    insert(
                        c,
                        "clinical_records",
                        "prescription_items",
                        prescription_item_id=ident(f"rx-item:{prefix}:{k}"),
                        prescription_id=rx,
                        tenant_id=cid,
                        medication_id=mid,
                        quantity=10 if k == 0 else 1,
                        display_name=name,
                        instructions=(
                            "DEMO ONLY: sample medicine instructions and follow-up text. Not a real"
                            " prescription; do not use for treatment."
                        ),
                    )
                mc = ident("mc:" + prefix)
                selected = status == "completed" and j % 2 == 0
                insert(
                    c,
                    "clinical_records",
                    "medical_certificates",
                    medical_certificate_id=mc,
                    **common,
                    selected=selected,
                    start_date=start.astimezone(ZoneInfo("Asia/Singapore")).date()
                    if selected
                    else None,
                    duration_days=2 if selected else None,
                    additional_notes=(
                        "DEMO SAMPLE ONLY. Not valid for work, school or clinical use."
                    ),
                    consultation_date=start.astimezone(ZoneInfo("Asia/Singapore")).date()
                    if issued
                    else None,
                    finalized_at=issued,
                    issued_at=issued if selected else None,
                    created_at=created,
                )
                if not issued:
                    continue
                doc_specs = [
                    ("prescription_pdf", "prescription_id", rx),
                    ("receipt_pdf", "payment_id", payid),
                ]
                if selected:
                    doc_specs.append(("medical_certificate_pdf", "medical_certificate_id", mc))
                oid = ident("order:" + prefix)
                qid = ident("quote:" + prefix)
                mpay = ident("medication-payment:" + prefix)
                delivery = ident("delivery:" + prefix)
                order_states = {
                    "delivered": ("delivered", "ready", "succeeded", "delivered"),
                    "preparing": ("paid", "not_ready", "succeeded", None),
                    "unpaid": ("awaiting_payment", "not_ready", "unpaid", None),
                    "in-transit": ("dispatched", "ready", "succeeded", "picked_up"),
                    "delivery-failed": (
                        "exception",
                        "ready",
                        "refund_required",
                        "failed",
                    ),
                    "cancelled-order": ("cancelled", "ready", "refunded", "cancelled"),
                    "delivery-uncertain": (
                        "exception",
                        "ready",
                        "refund_required",
                        "unknown",
                    ),
                }
                ostatus, medicine, payment, dstatus = order_states[scenario]
                subtotal = 1300
                delivery_fee = 780
                total = subtotal + delivery_fee
                insert(
                    c,
                    "fulfilment",
                    "orders",
                    order_id=oid,
                    tenant_id=cid,
                    patient_id=patient["subject_id"],
                    appointment_id=aid,
                    prescription_id=rx,
                    status=ostatus,
                    medicine_status=medicine,
                    payment_status=payment,
                    payment_id=mpay if payment != "unpaid" else None,
                    quote_id=qid,
                    delivery_id=delivery if dstatus else None,
                    medication_subtotal_minor=subtotal,
                    delivery_fee_minor=delivery_fee,
                    total_minor=total,
                    created_at=issued + timedelta(minutes=1),
                )
                for k, (mid, name, unit, price) in enumerate(medications[:2]):
                    qty = 10 if k == 0 else 1
                    insert(
                        c,
                        "fulfilment",
                        "order_items",
                        order_id=oid,
                        prescription_item_id=ident(f"rx-item:{prefix}:{k}"),
                        position=k,
                        medication_id=mid,
                        display_name=name,
                        quantity=qty,
                        unit_price_minor=price,
                        line_total_minor=qty * price,
                    )
                quote_created = now if scenario == "unpaid" else issued
                insert(
                    c,
                    "fulfilment",
                    "quotes",
                    quote_id=qid,
                    order_id=oid,
                    tenant_id=cid,
                    status="active" if scenario == "unpaid" else "accepted",
                    medication_subtotal_minor=subtotal,
                    delivery_fee_minor=delivery_fee,
                    total_minor=total,
                    created_at=quote_created,
                    expires_at=quote_created + timedelta(minutes=10),
                    items=Jsonb(
                        [
                            {
                                "display_name": m[1],
                                "quantity": 10 if k == 0 else 1,
                                "unit_price_minor": m[3],
                                "line_total_minor": m[3] * (10 if k == 0 else 1),
                            }
                            for k, m in enumerate(medications[:2])
                        ]
                    ),
                    destination=Jsonb(
                        {
                            "address_line": "DEMO ONLY - 10 Example Lane, unit 02-01",
                            "postal_code": "038983",
                            "country_code": "SG",
                        }
                    ),
                    provider_context=Jsonb(
                        {
                            "demo_seed": True,
                            "note": "Simulated quote only; no courier quote requested.",
                        }
                    ),
                )
                if dstatus:
                    insert(
                        c,
                        "fulfilment",
                        "deliveries",
                        delivery_id=delivery,
                        order_id=oid,
                        tenant_id=cid,
                        operation_id=ident("delivery-operation:" + prefix),
                        status=dstatus,
                        provider_order_id="DEMO-" + delivery[:18],
                        request_payload=Jsonb(
                            {"demo_seed": True, "note": "No courier request was sent."}
                        ),
                        provider_quote_expires_at=issued + timedelta(minutes=10),
                        attempts=1,
                        next_attempt_at=now + timedelta(days=3650),
                        send_started_at=issued + timedelta(minutes=2),
                        failure_code="provider_failed" if dstatus == "failed" else None,
                        resolution_reason="provider_failed"
                        if dstatus == "failed"
                        else "submission_uncertain"
                        if dstatus == "unknown"
                        else None,
                        resolution_delivered_at=issued + timedelta(minutes=3),
                        reconciled_at=issued + timedelta(minutes=3),
                        reconciled_by="demo_seed",
                        next_poll_at=now + timedelta(days=3650),
                        last_polled_at=issued + timedelta(minutes=3),
                        poll_attempts=1,
                        poll_error="provider_unavailable" if dstatus == "unknown" else None,
                        created_at=issued + timedelta(minutes=2),
                    )
                if payment != "unpaid":
                    comm = subtotal * clinic["commission_bps"] // 10000
                    insert(
                        c,
                        "billing",
                        "payments",
                        payment_id=mpay,
                        tenant_id=cid,
                        patient_id=patient["subject_id"],
                        purpose="medication_delivery",
                        order_id=oid,
                        quote_id=qid,
                        status="refunded"
                        if payment == "refunded"
                        else "refund_pending"
                        if payment == "refund_required"
                        else "succeeded",
                        resolution="refund_required" if payment == "refund_required" else "none",
                        amount_minor=total,
                        currency="SGD",
                        commissionable_minor=subtotal,
                        delivery_fee_minor=delivery_fee,
                        commission_bps=clinic["commission_bps"],
                        commission_amount_minor=comm,
                        clinic_amount_minor=total - comm,
                        provider="demo_seed",
                        provider_account_id="DEMO-NO-CHARGE",
                        provider_payment_id="DEMO-PAYMENT-" + mpay,
                        created_at=issued + timedelta(minutes=1),
                    )
                    if payment == "succeeded":
                        doc_specs.append(("receipt_pdf", "payment_id", mpay))
                order_manifest.append(
                    dict(
                        clinic=clinic["name"],
                        scenario=scenario,
                        order_id=oid,
                        tenant_id=cid,
                        patient_id=patient["subject_id"],
                    )
                )
                for n, (kind, field, source) in enumerate(doc_specs):
                    did = ident("document:" + source)
                    payload = dict(
                        clinic_name=clinic["name"] + " - DEMO SAMPLE",
                        clinic_address="10 Example Lane, Singapore - DEMONSTRATION ONLY",
                        patient_name=patient["display_name"],
                        reference="DEMO-" + did,
                        issued_at=(issued + timedelta(minutes=5)).isoformat(),
                    )
                    if kind == "prescription_pdf":
                        payload.update(
                            doctor_name=doc["display_name"],
                            doctor_registration="DEMO-REGISTRATION-0001",
                            items=[
                                dict(
                                    display_name=m[1],
                                    quantity=10 if k == 0 else 1,
                                    instructions=(
                                        "DEMONSTRATION ONLY. Not a real prescription; "
                                        "do not use for treatment."
                                    ),
                                )
                                for k, m in enumerate(medications[:2])
                            ],
                        )
                    elif kind == "receipt_pdf":
                        med = source == mpay
                        payload.update(
                            payment_reference="SIMULATED PAYMENT - no charge made",
                            paid_at=issued.isoformat(),
                            items=[
                                dict(
                                    description="Demo medication sample",
                                    amount_minor=subtotal,
                                ),
                                dict(
                                    description="Demo delivery sample",
                                    amount_minor=delivery_fee,
                                ),
                            ]
                            if med
                            else [
                                dict(
                                    description="Demo consultation sample",
                                    amount_minor=fee,
                                )
                            ],
                            total_minor=total if med else fee,
                        )
                    else:
                        payload.update(
                            doctor_name=doc["display_name"],
                            doctor_registration="DEMO-REGISTRATION-0001",
                            additional_notes="DEMO ONLY - not a valid medical certificate.",
                            consultation_date=start.date().isoformat(),
                            unfit_from=start.date().isoformat(),
                            unfit_through=(start + timedelta(days=1)).date().isoformat(),
                        )
                    pdf_jobs.append(
                        dict(
                            document_id=did,
                            kind=kind,
                            field=field,
                            source=source,
                            common=common,
                            payload=payload,
                            created_at=(issued + timedelta(minutes=5)).isoformat(),
                        )
                    )
            # Open slots across three days, plus a withdrawn sample.
            for d in range(1, 4):
                for hour in [13, 14, 15, 16]:
                    start = day + timedelta(days=d, hours=hour - 9)
                    insert(
                        c,
                        "scheduling",
                        "availability_slots",
                        slot_id=ident(f"open-slot:{idx}:{d}:{hour}"),
                        tenant_id=cid,
                        doctor_id=doc["subject_id"],
                        starts_at=start,
                        ends_at=start + timedelta(minutes=30),
                        withdrawn_at=now if d == 3 and hour == 16 else None,
                    )
        # Notification examples remain in local Floci SES, with finished jobs only.
        for idx, template in enumerate(["booking_confirmed", "document_ready", "delivery_updated"]):
            insert(
                c,
                "notification",
                "jobs",
                job_id=ident("notification:" + template),
                tenant_id=clinics[0]["tenant_id"],
                event_id=ident("notification-event:" + template),
                recipient_id=subjects["patient"]["subject_id"],
                recipient_email=subjects["patient"]["email"],
                template=template,
                status="sent",
                attempts=1,
                provider_message_id="DEMO-SES-" + str(idx),
                sent_at=now,
                send_started_at=now - timedelta(seconds=1),
            )
    print(
        "Reset all nine application schemas (migrations preserved) and seeded linked demo rows.",
        flush=True,
    )

    (STATE / "pdfs").mkdir(exist_ok=True)
    (STATE / "pdf-jobs.json").write_text(json.dumps(pdf_jobs, indent=2, default=str))
    subprocess.run(
        [
            str(ctx.document_python),
            str(ctx.source / "render.py"),
            "--root",
            str(ROOT),
            "--state",
            str(STATE),
        ],
        check=True,
    )
    with admin() as c:
        for spec in pdf_jobs:
            did = spec["document_id"]
            data = (STATE / "pdfs" / f"{did}.pdf").read_bytes()
            digest = hashlib.sha256(data).hexdigest()
            key = f"clean-demo/{did}.pdf"
            metadata = {
                "document-id": did,
                "tenant-id": spec["common"]["tenant_id"],
                "appointment-id": spec["common"]["appointment_id"],
                "patient-id": spec["common"]["patient_id"],
                "doctor-id": spec["common"]["doctor_id"],
                "sha256": digest,
                "demo-sample": "true",
            }
            s3.put_object(
                Bucket=doc_bucket,
                Key=key,
                Body=data,
                ContentType="application/pdf",
                ServerSideEncryption="AES256",
                CacheControl="no-store",
                Metadata=metadata,
            )
            insert(
                c,
                "document",
                "documents",
                document_id=did,
                **spec["common"],
                kind=spec["kind"],
                status="ready",
                storage_bucket=doc_bucket,
                storage_key=key,
                size_bytes=len(data),
                sha256=digest,
                created_at=datetime.fromisoformat(spec["created_at"]),
                **{spec["field"]: spec["source"]},
            )
    # Simple code-drawn demo logos, not copied brand artwork.
    for idx, clinic in enumerate(clinics):
        im = Image.new("RGB", (256, 256), clinic["primary_color"])
        draw = ImageDraw.Draw(im)
        draw.rounded_rectangle((30, 30, 226, 226), radius=45, fill="white")
        draw.rectangle((111, 68, 145, 188), fill=clinic["primary_color"])
        draw.rectangle((68, 111, 188, 145), fill=clinic["primary_color"])
        out = io.BytesIO()
        im.save(out, format="PNG")
        s3.put_object(
            Bucket=logo_bucket,
            Key=f"clinic-logos/{clinic['tenant_id']}/logo.png",
            Body=out.getvalue(),
            ContentType="image/png",
        )

    # Preserve configured Stripe sandbox account mappings, remapping only local clinic IDs.
    billing_path = ROOT / "services/billing/.env"
    billing = dotenv_values(billing_path)
    destinations = json.loads(billing.get("SERVICE_STRIPE_DESTINATIONS", "{}"))
    account = next(iter(destinations.values()), None) or billing.get("STRIPE_CONNECTED_ACCOUNT_ID")
    if account:
        set_key(
            str(billing_path),
            "SERVICE_STRIPE_DESTINATIONS",
            json.dumps({cl["tenant_id"]: account for cl in clinics[:2]}),
        )
    # Preserve directory structure and sandbox values; replace obsolete local IDs.
    fulfilment = dotenv_values(ROOT / "services/fulfilment/.env")
    for setting, section, ids in [
        (
            "SERVICE_DELIVERY_CONTACTS_PATH",
            "senders",
            [x["tenant_id"] for x in clinics[:2]],
        ),
        (
            "SERVICE_DELIVERY_CONTACTS_PATH",
            "recipients",
            [subjects[k]["subject_id"] for k in ["patient", "patient2"]],
        ),
    ]:
        path = fulfilment.get(setting)
        if path:
            path = ctx.local_file(path)
            data = json.loads(path.read_text())
            old = data.get(section, {})
            if old:
                example = next(iter(old.values()))
                data[section] = {key: example for key in ids}
                path.write_text(json.dumps(data, indent=2))
    ses = boto3.client("ses", **AWS)
    for email in [
        "notifications@telelink.test",
        *[s["email"] for s in subjects.values()],
    ]:
        ses.verify_email_identity(EmailAddress=email)
    for template in ["booking_confirmed", "document_ready", "delivery_updated"]:
        ses.send_email(
            Source="notifications@telelink.test",
            Destination={"ToAddresses": ["patient@example.test"]},
            Message={
                "Subject": {"Data": "DEMO ONLY: " + template},
                "Body": {
                    "Text": {
                        "Data": (
                            "Synthetic TeleLink notification example. No real consultation, charge "
                            "or delivery occurred. Open "
                        )
                        + ORIGIN
                    }
                },
            },
        )

    manifest = dict(
        generated_at=now.isoformat(),
        backup=str(backup),
        origin=ORIGIN,
        accounts=[
            dict(email=s["email"], name=s["display_name"], subject_id=s["subject_id"])
            for s in subjects.values()
        ],
        clinics=clinics,
        appointments=appointment_manifest,
        orders=order_manifest,
        documents=len(pdf_jobs),
        note="All payments and deliveries are synthetic examples. No Stripe or courier API called.",
    )
    (STATE / "manifest.json").write_text(json.dumps(manifest, indent=2, default=str))
    (STATE / "seed-complete.txt").write_text(now.isoformat())
    print(
        f"Seed complete: {len(accounts)} accounts, {len(clinics)} clinics, "
        f"{len(appointment_manifest)} appointments, {len(order_manifest)} orders "
        f"and {len(pdf_jobs)} PDF documents.",
        flush=True,
    )
