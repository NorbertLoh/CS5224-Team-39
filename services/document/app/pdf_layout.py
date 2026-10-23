"""Shared print layout using bundled fonts and escaped, glyph-checked text."""

from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape
from zoneinfo import ZoneInfo

import reportlab
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
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
INK = colors.black
MUTED = colors.black
LINE = colors.black
PALE = colors.white
MARGIN = 46
# Platypus frames reserve six points of inner padding on each side.
WIDTH = A4[0] - 2 * MARGIN - 12
SG = ZoneInfo("Asia/Singapore")


def paragraph(value, *, bold=False, size=10, color=INK, after=6, right=False, center=False):
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
            alignment=TA_CENTER if center else TA_RIGHT if right else TA_LEFT,
            splitLongWords=True,
        ),
    )


def section(title):
    return paragraph(title, bold=True, size=11, after=10)


def date_time(value):
    return f"{value.astimezone(SG):%d %b %Y, %H:%M} SGT"


def info_grid(fields, *, width=WIDTH):
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
        colWidths=[width / 2] * 2,
        hAlign="LEFT",
    )
    table.setStyle(
        [
            ("BACKGROUND", (0, 0), (-1, -1), PALE),
            ("GRID", (0, 0), (-1, -1), 0.5, LINE),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 12),
            ("RIGHTPADDING", (0, 0), (-1, -1), 12),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
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
            ("TOPPADDING", (0, 0), (-1, -1), 7),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ]
    )
    return table


def render(title, snapshot, body, *, fields=()):
    output = BytesIO()
    story = [paragraph(snapshot.clinic_name, bold=True, size=16, after=4, center=True)]
    if snapshot.clinic_address:
        story.append(paragraph(snapshot.clinic_address, size=9, after=10, center=True))
    story.extend(
        [
            HRFlowable(width="100%", thickness=0.7, color=INK, spaceBefore=6, spaceAfter=18),
            paragraph(title.upper(), bold=True, size=15, after=20, center=True),
            info_grid(
                [
                    ("Patient", snapshot.patient_name),
                    ("Issued", date_time(snapshot.issued_at)),
                    ("Document reference", snapshot.reference),
                    *fields,
                ]
            ),
            Spacer(1, 18),
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
