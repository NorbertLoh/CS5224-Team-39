"""Formal clinic documents from validated snapshots; no generation side effects."""

from reportlab.platypus import KeepTogether, Spacer, Table

from app.pdf_layout import INK, PALE, WIDTH, date_time, info_grid, line_table, paragraph, section
from app.pdf_layout import render as _render
from app.template_data import MedicalCertificate, Prescription, Receipt


def _doctor(data):
    return data.doctor_name + (
        f"\nMedical registration: {data.doctor_registration}" if data.doctor_registration else ""
    )


def render_prescription(data: Prescription) -> bytes:
    rows = [
        [
            paragraph(str(number), size=9),
            [
                paragraph(item.display_name, bold=True),
                paragraph(f"Directions: {item.instructions}"),
            ],
            paragraph(f"Quantity: {item.quantity}", size=9),
        ]
        for number, item in enumerate(data.items, 1)
    ]
    return _render(
        "Prescription",
        data,
        [
            section("Prescribed medicines"),
            line_table(["No.", "Medicine and directions", "Quantity"], rows, [40, WIDTH - 128, 88]),
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
                paragraph("Total paid", bold=True, size=12, after=0),
                paragraph(_money(data.total_minor), bold=True, size=15, after=0, right=True),
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
        section("Certification"),
        paragraph(
            f"This certifies that {data.patient_name} is medically unfit for duty "
            f"from {data.unfit_from:%d %b %Y} to {data.unfit_through:%d %b %Y} "
            f"(inclusive, {days} day(s)).",
            size=11.5,
            after=18,
        ),
        info_grid(
            [
                ("Unfit from", f"{data.unfit_from:%d %b %Y}"),
                ("Unfit through (inclusive)", f"{data.unfit_through:%d %b %Y}"),
            ]
        ),
        Spacer(1, 22),
    ]
    if data.additional_notes:
        body.extend([section("Additional notes"), paragraph(data.additional_notes), Spacer(1, 16)])
    body.append(KeepTogether([section("Issued by"), paragraph(_doctor(data))]))
    return _render(
        "Medical Certificate",
        data,
        body,
        fields=[("Consultation date", f"{data.consultation_date:%d %b %Y}")],
    )
