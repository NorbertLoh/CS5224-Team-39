"""P01 document metadata, isolated from other services.

Revision ID: 0001
Revises:
"""

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "documents",
        sa.Column("document_id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("appointment_id", sa.Uuid(), nullable=False),
        sa.Column("patient_id", sa.Uuid(), nullable=False),
        sa.Column("doctor_id", sa.Uuid()),
        sa.Column("prescription_id", sa.Uuid()),
        sa.Column("payment_id", sa.Uuid()),
        sa.Column("medical_certificate_id", sa.Uuid()),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), server_default=sa.text("'pending'"), nullable=False),
        sa.Column(
            "content_type", sa.Text(), server_default=sa.text("'application/pdf'"), nullable=False
        ),
        sa.Column("storage_bucket", sa.Text()),
        sa.Column("storage_key", sa.Text()),
        sa.Column("size_bytes", sa.BigInteger()),
        sa.Column("sha256", sa.Text()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "(kind = 'prescription_pdf' AND prescription_id IS NOT NULL "
            "AND payment_id IS NULL AND medical_certificate_id IS NULL AND doctor_id IS NOT NULL) "
            "OR (kind = 'receipt_pdf' AND payment_id IS NOT NULL "
            "AND prescription_id IS NULL AND medical_certificate_id IS NULL) "
            "OR (kind = 'medical_certificate_pdf' AND medical_certificate_id IS NOT NULL "
            "AND prescription_id IS NULL AND payment_id IS NULL AND doctor_id IS NOT NULL)",
            name="ck_documents_source",
        ),
        sa.CheckConstraint("status IN ('pending', 'ready', 'failed')", name="ck_documents_status"),
        sa.CheckConstraint("content_type = 'application/pdf'", name="ck_documents_content_type"),
        sa.CheckConstraint(
            "(status = 'ready' AND storage_bucket IS NOT NULL AND btrim(storage_bucket) <> '' "
            "AND storage_key IS NOT NULL AND btrim(storage_key) <> '' "
            "AND size_bytes IS NOT NULL AND size_bytes > 0 "
            "AND sha256 IS NOT NULL AND sha256 ~ '^[0-9a-f]{64}$') "
            "OR (status IN ('pending', 'failed') AND storage_bucket IS NULL "
            "AND storage_key IS NULL AND size_bytes IS NULL AND sha256 IS NULL)",
            name="ck_documents_storage",
        ),
        sa.UniqueConstraint(
            "tenant_id", "kind", "prescription_id", name="uq_documents_prescription"
        ),
        sa.UniqueConstraint("tenant_id", "kind", "payment_id", name="uq_documents_payment"),
        sa.UniqueConstraint(
            "tenant_id", "kind", "medical_certificate_id", name="uq_documents_medical_certificate"
        ),
        sa.UniqueConstraint("storage_bucket", "storage_key", name="uq_documents_object"),
        schema="document",
    )
    op.create_index(
        "ix_documents_patient_page",
        "documents",
        ["tenant_id", "patient_id", "created_at", "document_id"],
        schema="document",
    )
    op.create_index(
        "ix_documents_appointment_page",
        "documents",
        ["tenant_id", "appointment_id", "created_at", "document_id"],
        schema="document",
    )
    op.execute("""
        CREATE FUNCTION document.touch_document() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            NEW.created_at = OLD.created_at;
            NEW.updated_at = clock_timestamp();
            RETURN NEW;
        END;
        $$
    """)
    op.execute("""
        CREATE TRIGGER touch_document BEFORE UPDATE ON document.documents
        FOR EACH ROW EXECUTE FUNCTION document.touch_document()
    """)


def downgrade():
    op.drop_table("documents", schema="document")
    op.execute("DROP FUNCTION document.touch_document()")
