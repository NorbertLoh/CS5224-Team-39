"""Formal clinic documents from validated snapshots; no generation side effects."""

from reportlab.platypus import KeepTogether, LongTable, Spacer, Table

from app.rendering.pdf_layout import (
    INK,
    PALE,
    WIDTH,
    date_time,
    info_grid,
    line_table,
    paragraph,
    section,
)
from app.rendering.pdf_layout import render as _render
from app.rendering.template_data import MedicalCertificate, Prescription, Receipt


def _doctor(data):
    return data.doctor_name + (
        f"\nMedical registration: {data.doctor_registration}" if data.doctor_registration else ""
    )


def render_prescription(data: Prescription) -> bytes:
    rows = [
        [
            paragraph(str(number), size=9),
            paragraph(item.display_name, bold=True),
            paragraph(item.instructions),
            paragraph(f"Quantity: {item.quantity}", size=9),
        ]
        for number, item in enumerate(data.items, 1)
    ]
    return _render(
        "Prescription",
        data,
        [
            section("Prescribed medicines"),
            line_table(
                ["No.", "Medicine", "Directions", "Quantity"],
                rows,
                [36, 150, WIDTH - 274, 88],
            ),
        ],
        fields=[("Prescribing clinician", _doctor(data))],
    )


def _money(minor: int) -> str:
    return f"SGD {minor // 100:,}.{minor % 100:02d}"


def render_receipt(data: Receipt) -> bytes:
    rows = [
        [paragraph(item.description), paragraph(_money(item.amount_minor), right=True)]
        for item in data.items
    ]
    total = Table(
        [
            [
                paragraph("Total paid", bold=True, size=11, after=0),
                paragraph(_money(data.total_minor), bold=True, size=12, after=0, right=True),
            ]
        ],
        colWidths=[WIDTH - 160, 160],
        hAlign="LEFT",
    )
    total.setStyle(
        [
            ("BACKGROUND", (0, 0), (-1, -1), PALE),
            ("LINEABOVE", (0, 0), (-1, 0), 1, INK),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 14),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 14),
            ("LEFTPADDING", (0, 0), (-1, -1), 10),
            ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ]
    )
    return _render(
        "Receipt",
        data,
        [
            section("Payment received"),
            paragraph(f"Paid: {date_time(data.paid_at)}"),
            Spacer(1, 8),
            line_table(["Description", "Amount"], rows, [WIDTH - 125, 125]),
            KeepTogether([Spacer(1, 16), total]),
        ],
        fields=[("Payment reference", data.payment_reference)],
    )


def render_medical_certificate(data: MedicalCertificate) -> bytes:
    days = (data.unfit_through - data.unfit_from).days + 1
    body = [
        paragraph(
            "This is to certify that the above-named patient is medically unfit for duty "
            f"from {data.unfit_from:%d %b %Y} to {data.unfit_through:%d %b %Y} "
            f"(inclusive, {days} day(s)).",
            size=11,
            after=18,
        ),
        info_grid(
            [
                ("Unfit from", f"{data.unfit_from:%d %b %Y}"),
                ("Unfit through (inclusive)", f"{data.unfit_through:%d %b %Y}"),
            ],
            width=WIDTH - 32,
        ),
        Spacer(1, 22),
    ]
    if data.additional_notes:
        body.extend([section("Additional notes"), paragraph(data.additional_notes), Spacer(1, 16)])
    certificate = LongTable(
        [[item] for item in body],
        colWidths=[WIDTH],
        splitByRow=1,
        splitInRow=1,
        hAlign="LEFT",
    )
    certificate.setStyle(
        [
            ("BOX", (0, 0), (-1, -1), 0.5, INK),
            ("LEFTPADDING", (0, 0), (-1, -1), 16),
            ("RIGHTPADDING", (0, 0), (-1, -1), 16),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ]
    )
    return _render(
        "Medical Certificate",
        data,
        [
            certificate,
            Spacer(1, 14),
            KeepTogether(
                [info_grid([("Hospital / clinic", data.clinic_name), ("Issued by", _doctor(data))])]
            ),
        ],
        fields=[("Consultation date", f"{data.consultation_date:%d %b %Y}")],
    )
