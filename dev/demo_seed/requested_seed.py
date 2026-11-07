"""Requested five-account seed shared by local provisioning and AWS demo reset."""

from io import BytesIO

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen.canvas import Canvas

ACCOUNTS = (
    ("patient@example.test", "Local Patient", ["patient"]),
    ("lohnorbert@gmail.com", "Norbert", ["patient"]),
    ("doctor@example.test", "Dr. Tan", []),
    ("clinic@example.test", "Local Clinic Admin", []),
    ("platform@example.test", "Local Platform Admin", ["platform_admin"]),
)
PATIENT_ADDRESS = {
    "address_line": "3 Temasek Boulevard, Singapore",
    "postal_code": "038983",
    "country_code": "SG",
}

SLUG = "meridian-health-partners"


def application(phone):
    return {
        "slug": SLUG,
        "name": "Meridian Health Partners",
        "branding": {
            "primary_color": "#156B63",
            "logo_url": None,
            "description": "Your trusted family clinic since 1990.",
        },
        "consultation_price": {"amount_minor": 3000, "currency": "SGD"},
        "location": {
            "address_line": "1 Raffles Place, Singapore",
            "postal_code": "048616",
            "country_code": "SG",
            "coordinates": {"lat": "1.2844", "lng": "103.8511"},
            "pickup_contact": {"name": "Norbert", "phone": phone},
        },
    }


FIELDS = {
    "legal_name": "Dr. Tan",
    "licence_number": "DEMO-TAN-0001",
    "licensing_authority": "Telelink Demo Medical Registry (fictional)",
    "specialty": "General Practice (Demo)",
}


def licence_pdf():
    output = BytesIO()
    pdf = Canvas(output, pagesize=A4, invariant=1)
    width, height = A4
    pdf.setTitle("Dr. Tan - DEMO ONLY - Sample licence evidence")
    pdf.setAuthor("Telelink local demonstration")
    pdf.setFillColor(HexColor("#153F3A"))
    pdf.rect(0, height - 160, width, 160, fill=1, stroke=0)
    pdf.setFillColor(HexColor("#FFFFFF"))
    pdf.setFont("Helvetica-Bold", 24)
    pdf.drawString(48, height - 70, "SAMPLE DOCTOR LICENCE")
    pdf.setFont("Helvetica-Bold", 14)
    pdf.drawString(48, height - 105, "DEMO ONLY - NOT VALID FOR PRACTICE")
    pdf.setFillColor(HexColor("#172B28"))
    pdf.setFont("Helvetica-Bold", 28)
    pdf.drawString(48, height - 220, FIELDS["legal_name"])
    rows = [
        ("Sample licence number", FIELDS["licence_number"]),
        ("Fictional issuing body", FIELDS["licensing_authority"]),
        ("Demo specialty", FIELDS["specialty"]),
        ("Sample issue date", "1 January 2026"),
        ("Sample expiry date", "31 December 2030"),
    ]
    y = height - 280
    for label, value in rows:
        pdf.setFont("Helvetica-Bold", 10)
        pdf.drawString(48, y, label.upper())
        pdf.setFont("Helvetica", 12)
        pdf.drawString(48, y - 21, value)
        y -= 72
    pdf.setStrokeColor(HexColor("#CDDAD7"))
    pdf.line(48, 145, width - 48, 145)
    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawString(48, 119, "FICTIONAL EVIDENCE FOR LOCAL SOFTWARE TESTING")
    pdf.setFont("Helvetica", 10)
    pdf.drawString(48, 97, "This document is not issued by a medical regulator.")
    pdf.drawString(
        48, 80, "It confers no qualification, registration or authority to practise medicine."
    )
    pdf.save()
    return output.getvalue()
