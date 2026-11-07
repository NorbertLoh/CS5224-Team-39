"""Requested demo rows shared by local and AWS reset workers."""

from uuid import NAMESPACE_URL, uuid5

from psycopg import sql
from psycopg.types.json import Jsonb
from requested_seed import ACCOUNTS, FIELDS, PATIENT_ADDRESS, application

SCHEMAS = (
    "identity",
    "tenant",
    "scheduling",
    "consultation",
    "clinical_records",
    "billing",
    "fulfilment",
    "document",
    "notification",
)


def seed_id(name):
    return uuid5(NAMESPACE_URL, "telelink:requested-demo:" + name)


def insert(connection, schema, table, **values):
    connection.execute(
        sql.SQL("INSERT INTO {}.{} ({}) VALUES ({})").format(
            sql.Identifier(schema),
            sql.Identifier(table),
            sql.SQL(",").join(map(sql.Identifier, values)),
            sql.SQL(",").join(sql.Placeholder() for _ in values),
        ),
        list(values.values()),
    )


def seed_database(connection, users, phone, evidence):
    """All application rows are replaced together, with no CASCADE outside the allowlist."""
    tables = connection.execute(
        "SELECT schemaname, tablename FROM pg_tables WHERE schemaname=ANY(%s) "
        "AND tablename <> 'alembic_version' ORDER BY schemaname, tablename",
        (list(SCHEMAS),),
    ).fetchall()
    if set(s for s, _ in tables) != set(SCHEMAS):
        raise ValueError("All nine migrated application schemas are required")
    connection.execute(
        sql.SQL("TRUNCATE {} RESTART IDENTITY").format(
            sql.SQL(",").join(
                sql.SQL("{}.{}").format(sql.Identifier(s), sql.Identifier(t)) for s, t in tables
            )
        )
    )
    ids = {}
    for email, name, roles in ACCOUNTS:
        user = users[email]
        ids[email] = user["subject_id"]
        insert(
            connection,
            "identity",
            "subjects",
            subject_id=user["subject_id"],
            cognito_sub=user["sub"],
            display_name=name,
            email=email,
            global_roles=roles,
        )
        if "patient" in roles:
            insert(
                connection,
                "identity",
                "patient_profiles",
                subject_id=user["subject_id"],
                phone_number=phone,
                **PATIENT_ADDRESS,
            )
    clinic = application(phone)
    tenant_id = seed_id("meridian")
    admin = ids["clinic@example.test"]
    doctor = ids["doctor@example.test"]
    insert(
        connection,
        "tenant",
        "clinics",
        tenant_id=tenant_id,
        slug=clinic["slug"],
        name=clinic["name"],
        status="pending_review",
        creator_subject_id=admin,
        membership_provisioned=True,
        primary_color=clinic["branding"]["primary_color"],
        description=clinic["branding"]["description"],
        consultation_price_minor=3000,
        currency="SGD",
        commission_bps=0,
    )
    insert(
        connection,
        "tenant",
        "clinic_locations",
        tenant_id=tenant_id,
        location=Jsonb(clinic["location"]),
        updated_by=admin,
    )
    for subject, role in ((admin, "clinic_admin"), (doctor, "doctor")):
        insert(
            connection,
            "identity",
            "memberships",
            membership_id=seed_id(role),
            subject_id=subject,
            tenant_id=tenant_id,
            roles=[role],
            status="active",
        )
    document_id = seed_id("doctor-licence")
    insert(
        connection,
        "identity",
        "doctor_documents",
        document_id=document_id,
        subject_id=doctor,
        content_type="application/pdf",
        content=evidence,
        filename="Dr. Tan - Licence.pdf",
    )
    insert(
        connection,
        "identity",
        "doctor_applications",
        subject_id=doctor,
        document_id=document_id,
        status="pending",
        revision=1,
        **FIELDS,
    )
    snapshot = connection.execute(
        "SELECT to_jsonb(a) FROM identity.doctor_applications a WHERE subject_id=%s",
        (doctor,),
    ).fetchone()[0]
    insert(
        connection,
        "identity",
        "doctor_application_events",
        event_id=seed_id("submitted"),
        subject_id=doctor,
        actor_id=doctor,
        action="submitted",
        snapshot=Jsonb(snapshot),
    )
    counts = connection.execute(
        "SELECT (SELECT count(*) FROM identity.subjects), "
        "(SELECT count(*) FROM tenant.clinics WHERE status='pending_review'), "
        "(SELECT count(*) FROM identity.doctor_applications WHERE status='pending'), "
        "(SELECT count(*) FROM identity.memberships WHERE status='active')"
    ).fetchone()
    if counts != (5, 1, 1, 2):
        raise ValueError("Seed verification failed")
    stored = connection.execute(
        "SELECT content FROM identity.doctor_documents WHERE document_id=%s",
        (document_id,),
    ).fetchone()[0]
    if bytes(stored) != evidence:
        raise ValueError("Evidence verification failed")


def seed_users(connection, client, pool, password, actor_id):
    users = {}
    for email, name, _ in ACCOUNTS:
        created = False
        try:
            user = client.admin_get_user(UserPoolId=pool, Username=email)
        except client.exceptions.UserNotFoundException:
            client.admin_create_user(
                UserPoolId=pool,
                Username=email,
                MessageAction="SUPPRESS",
                TemporaryPassword=password,
                UserAttributes=[
                    {"Name": "email", "Value": email},
                    {"Name": "email_verified", "Value": "true"},
                    {"Name": "name", "Value": name},
                ],
            )
            user = client.admin_get_user(UserPoolId=pool, Username=email)
            created = True
        attrs = {a["Name"]: a["Value"] for a in user["UserAttributes"]}
        if (
            attrs.get("email") != email
            or attrs.get("email_verified") != "true"
            or not user["Enabled"]
        ):
            raise ValueError("A seed account is disabled or has unexpected attributes")
        if user["UserStatus"] not in {"CONFIRMED", "FORCE_CHANGE_PASSWORD"}:
            raise ValueError("A seed account has an unsupported authentication state")
        if created or user["UserStatus"] == "FORCE_CHANGE_PASSWORD":
            client.admin_set_user_password(
                UserPoolId=pool,
                Username=user["Username"],
                Password=password,
                Permanent=True,
            )
        row = connection.execute(
            "SELECT subject_id FROM identity.subjects WHERE cognito_sub=%s",
            (attrs["sub"],),
        ).fetchone()
        users[email] = {"sub": attrs["sub"], "subject_id": row[0] if row else seed_id(email)}
    if str(users["platform@example.test"]["subject_id"]) != str(actor_id):
        raise ValueError("The reset would remove its requesting administrator")
    return users
