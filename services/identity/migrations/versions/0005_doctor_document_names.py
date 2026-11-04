"""Persist descriptive licence filenames, including existing supporting files."""

import unicodedata

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("doctor_documents", sa.Column("filename", sa.Text()), schema="identity")
    connection = op.get_bind()
    rows = (
        connection.execute(
            sa.text("""
        SELECT d.document_id, d.content_type, COALESCE(
            (SELECT e.snapshot->>'legal_name' FROM identity.doctor_application_events e
             WHERE e.snapshot->>'document_id' = d.document_id::text
             ORDER BY e.created_at, e.event_id LIMIT 1),
            a.legal_name, s.display_name, 'Doctor') AS doctor_name
        FROM identity.doctor_documents d
        JOIN identity.subjects s ON s.subject_id = d.subject_id
        LEFT JOIN identity.doctor_applications a ON a.document_id = d.document_id
    """)
        )
        .mappings()
        .all()
    )
    # Freeze the naming policy here so historical migrations do not import live app code.
    for row in rows:
        name = unicodedata.normalize("NFKC", row["doctor_name"])
        name = "".join(char for char in name if char.isalnum() or char in " .-_' ")
        name = " ".join(name.split()).strip(". ")[:180].rstrip(". ") or "Doctor"
        extension = {"application/pdf": "pdf", "image/png": "png", "image/jpeg": "jpg"}[
            row["content_type"]
        ]
        connection.execute(
            sa.text("""
            UPDATE identity.doctor_documents SET filename = :filename
            WHERE document_id = :document_id
        """),
            {"filename": f"{name} - licence.{extension}", "document_id": row["document_id"]},
        )


def downgrade():
    op.drop_column("doctor_documents", "filename", schema="identity")
