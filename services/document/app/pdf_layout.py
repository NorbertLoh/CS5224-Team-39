"""Shared print layout using bundled fonts and escaped, glyph-checked text."""

from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape
from zoneinfo import ZoneInfo

import reportlab
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import HRFlowable, LongTable, Paragraph, SimpleDocTemplate, Spacer, Table

FONT = "TelelinkVera"
BOLD = "TelelinkVeraBold"
_FONTS = Path(reportlab.__file__).parent / "fonts"
pdfmetrics.registerFont(TTFont(FONT, str(_FONTS / "Vera.ttf")))
pdfmetrics.registerFont(TTFont(BOLD, str(_FONTS / "VeraBd.ttf")))
INK = colors.HexColor("#183D3B")
MUTED = colors.HexColor("#53615F")
LINE = colors.HexColor("#D5DDDB")
PALE = colors.HexColor("#F3F6F5")
MARGIN = 46
WIDTH = A4[0] - 2 * MARGIN
SG = ZoneInfo("Asia/Singapore")


def paragraph(value, *, bold=False, size=10, color=INK, after=6, right=False):
    font = BOLD if bold else FONT
    glyphs = pdfmetrics.getFont(font).face.charToGlyph
    if any(ord(char) not in glyphs for char in value if char not in "\n\t"):
        raise ValueError("Text contains characters unsupported by the bundled PDF font")
    safe = escape(value).replace("\n", "<br/>").replace("\t", "    ")
    return Paragraph(
        safe,
        ParagraphStyle(
            "label" if bold else "body",
            fontName=font,
            fontSize=size,
            leading=size * 1.5,
            spaceAfter=after,
            textColor=color,
            alignment=TA_RIGHT if right else TA_LEFT,
            splitLongWords=True,
        ),
    )


def section(title):
    return paragraph(title, bold=True, size=11, after=10)


def date_time(value):
    return f"{value.astimezone(SG):%d %b %Y, %H:%M} SGT"


def info_grid(fields):
    cells = [
        [
            paragraph(label.upper(), bold=True, size=7.5, color=MUTED, after=3),
            paragraph(value, after=0),
        ]
        for label, value in fields
    ]
    if len(cells) % 2:
        cells.append("")
    table = Table(
        [cells[index : index + 2] for index in range(0, len(cells), 2)],
        colWidths=[WIDTH / 2] * 2,
        hAlign="LEFT",
    )
    table.setStyle(
        [
            ("BACKGROUND", (0, 0), (-1, -1), PALE),
            ("BOX", (0, 0), (-1, -1), 0.5, LINE),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 12),
            ("RIGHTPADDING", (0, 0), (-1, -1), 12),
            ("TOPPADDING", (0, 0), (-1, -1), 9),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 11),
        ]
    )
    return table


def line_table(headers, rows, widths):
    table = LongTable(
        [[paragraph(label, bold=True, size=9, after=0) for label in headers], *rows],
        colWidths=widths,
        repeatRows=1,
        splitByRow=1,
        splitInRow=1,
        hAlign="LEFT",
    )
    table.setStyle(
        [
            ("BACKGROUND", (0, 0), (-1, 0), PALE),
            ("LINEABOVE", (0, 0), (-1, 0), 0.7, INK),
            ("LINEBELOW", (0, 0), (-1, 0), 0.7, INK),
            ("LINEBELOW", (0, 1), (-1, -1), 0.4, LINE),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 9),
            ("RIGHTPADDING", (0, 0), (-1, -1), 9),
            ("TOPPADDING", (0, 0), (-1, -1), 10),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ]
    )
    return table


def render(title, snapshot, body, *, fields=()):
    output = BytesIO()
    story = [paragraph(snapshot.clinic_name, bold=True, size=19, after=4)]
    if snapshot.clinic_address:
        story.append(paragraph(snapshot.clinic_address, size=9, color=MUTED, after=10))
    story.extend(
        [
            HRFlowable(width="100%", thickness=1.3, color=INK, spaceBefore=6, spaceAfter=16),
            paragraph(title, bold=True, size=23, after=15),
            info_grid(
                [
                    ("Patient", snapshot.patient_name),
                    ("Issued", date_time(snapshot.issued_at)),
                    ("Document reference", snapshot.reference),
                    *fields,
                ]
            ),
            Spacer(1, 22),
            *body,
        ]
    )

    def furniture(canvas, document):
        canvas.saveState()
        canvas.setStrokeColor(LINE)
        canvas.line(MARGIN, 39, A4[0] - MARGIN, 39)
        canvas.setFillColor(MUTED)
        canvas.setFont(FONT, 8)
        canvas.drawString(MARGIN, 25, "Private and confidential")
        canvas.drawRightString(A4[0] - MARGIN, 25, f"Page {document.page}")
        if document.page > 1:
            canvas.setFont(BOLD, 8)
            canvas.drawString(MARGIN, A4[1] - 29, f"{title} - continued")
        canvas.restoreState()

    SimpleDocTemplate(
        output,
        pagesize=A4,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=MARGIN,
        bottomMargin=58,
        title=title,
        author="",
        subject="",
        creator="TeleLink Health",
    ).build(story, onFirstPage=furniture, onLaterPages=furniture)
    return output.getvalue()
