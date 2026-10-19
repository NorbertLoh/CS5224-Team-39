"""Small paginated PDFs. No network, persistence, signatures or generation side effects."""

from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape
from zoneinfo import ZoneInfo

import reportlab
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

from app.template_data import MedicalCertificate, Prescription, Receipt

_FONT = "TelelinkVera"
_FONT_BOLD = "TelelinkVeraBold"
# Vera and its licence ship with ReportLab; no host-specific font/network dependency.
_FONTS = Path(reportlab.__file__).parent / "fonts"
pdfmetrics.registerFont(TTFont(_FONT, str(_FONTS / "Vera.ttf")))
pdfmetrics.registerFont(TTFont(_FONT_BOLD, str(_FONTS / "VeraBd.ttf")))
_SG = ZoneInfo("Asia/Singapore")


def _paragraph(value: str, *, heading: bool = False) -> Paragraph:
    # Reject missing glyphs instead of silently losing patient names/instructions.
    font_name = _FONT_BOLD if heading else _FONT
    glyphs = pdfmetrics.getFont(font_name).face.charToGlyph
    if any(ord(char) not in glyphs for char in value if char not in "\n\t"):
        raise ValueError("Text contains characters unsupported by the bundled PDF font")
    safe = escape(value).replace("\n", "<br/>").replace("\t", "    ")
    return Paragraph(
        safe,
        ParagraphStyle(
            "heading" if heading else "body",
            fontName=font_name,
            fontSize=15 if heading else 10,
            leading=21 if heading else 15,
            spaceAfter=10,
            alignment=TA_LEFT,
            textColor=colors.HexColor("#163C3A"),
            splitLongWords=True,
        ),
    )


def _render(title, snapshot, body) -> bytes:
    output = BytesIO()
    story = [
        _paragraph(snapshot.clinic_name, heading=True),
        *([_paragraph(snapshot.clinic_address)] if snapshot.clinic_address else []),
        Spacer(1, 12),
        _paragraph(title, heading=True),
        _paragraph(f"Reference: {snapshot.reference}"),
        _paragraph(f"Issued: {snapshot.issued_at.astimezone(_SG):%d %b %Y, %H:%M} SGT"),
        _paragraph(f"Patient: {snapshot.patient_name}"),
        *body,
    ]

    def footer(canvas, document):
        canvas.saveState()
        canvas.setFont(_FONT, 8)
        canvas.drawString(42, 24, "Private and confidential")
        canvas.drawRightString(A4[0] - 42, 24, f"Page {document.page}")
        canvas.restoreState()

    SimpleDocTemplate(
        output,
        pagesize=A4,
        leftMargin=42,
        rightMargin=42,
        topMargin=42,
        bottomMargin=48,
        title=title,
        author="",  # Avoid adding patient data to PDF properties.
    ).build(story, onFirstPage=footer, onLaterPages=footer)
    return output.getvalue()


def render_prescription(data: Prescription) -> bytes:
    registration = f" ({data.doctor_registration})" if data.doctor_registration else ""
    body = [_paragraph(f"Doctor: {data.doctor_name}{registration}")]
    for number, item in enumerate(data.items, 1):
        body.extend(
            [
                _paragraph(f"{number}. {item.display_name} | Quantity: {item.quantity}"),
                _paragraph(f"Instructions: {item.instructions}"),
                Spacer(1, 6),
            ]
        )
    return _render("Prescription", data, body)


def _money(minor: int) -> str:
    return f"SGD {minor // 100:,}.{minor % 100:02d}"


def render_receipt(data: Receipt) -> bytes:
    body = [
        _paragraph(f"Payment reference: {data.payment_reference}"),
        _paragraph(f"Paid: {data.paid_at.astimezone(_SG):%d %b %Y, %H:%M} SGT"),
        *[_paragraph(f"{item.description}: {_money(item.amount_minor)}") for item in data.items],
        _paragraph(f"Total paid: {_money(data.total_minor)}", heading=True),
    ]
    return _render("Receipt", data, body)


def render_medical_certificate(data: MedicalCertificate) -> bytes:
    days = (data.unfit_through - data.unfit_from).days + 1
    body = [
        _paragraph(f"Consultation date: {data.consultation_date:%d %b %Y}"),
        _paragraph(
            f"This certifies that {data.patient_name} is medically unfit for duty "
            f"from {data.unfit_from:%d %b %Y} to {data.unfit_through:%d %b %Y} "
            f"(inclusive, {days} day(s))."
        ),
        _paragraph(f"Issued by: {data.doctor_name}"),
        *(
            [_paragraph(f"Medical registration: {data.doctor_registration}")]
            if data.doctor_registration
            else []
        ),
        *(
            [_paragraph(f"Additional notes: {data.additional_notes}")]
            if data.additional_notes
            else []
        ),
    ]
    return _render("Medical Certificate", data, body)
