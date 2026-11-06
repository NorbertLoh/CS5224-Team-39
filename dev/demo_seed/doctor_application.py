"""Fictional, pending doctor application and clearly marked sample PDF evidence."""

from io import BytesIO
from pathlib import Path

import httpx
from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen.canvas import Canvas

FIELDS = {
    "legal_name": "Dr. Tan",
    "licence_number": "DEMO-TAN-0001",
    "licensing_authority": "Telelink Demo Medical Registry (fictional)",
    "specialty": "General Practice (Demo)",
}
PDF_PATH = Path("/state/output/pdf/dr-tan-demo-licence.pdf")


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


def doctor_application(cognito, client_id, password, *, apply):
    auth = cognito.initiate_auth(
        ClientId=client_id,
        AuthFlow="USER_PASSWORD_AUTH",
        AuthParameters={"USERNAME": "doctor@example.test", "PASSWORD": password},
    )
    headers = {"Authorization": "Bearer " + auth["AuthenticationResult"]["AccessToken"]}
    expected_pdf = licence_pdf()
    with httpx.Client(timeout=30, trust_env=False, headers=headers) as http:
        response = http.get("http://identity:8000/me/doctor-application")
        response.raise_for_status()
        application = response.json()
        if apply:
            PDF_PATH.parent.mkdir(parents=True, exist_ok=True)
            PDF_PATH.write_bytes(expected_pdf)
        if application is None and apply:
            response = http.post(
                "http://identity:8000/me/doctor-documents",
                content=expected_pdf,
                headers={"Content-Type": "application/pdf"},
            )
            response.raise_for_status()
            document_id = response.json()["document_id"]
            response = http.post(
                "http://identity:8000/me/doctor-application",
                json={**FIELDS, "document_id": document_id, "expected_revision": 0},
            )
            response.raise_for_status()
            application = response.json()
        if application is None or any(application[key] != value for key, value in FIELDS.items()):
            raise ValueError("The doctor's application differs from the requested demo.")
        if application["status"] != "pending":
            raise ValueError("The doctor has already been reviewed; the decision was preserved.")
        response = http.get("http://identity:8000/doctor-documents/" + application["document_id"])
        response.raise_for_status()
        if response.content != expected_pdf:
            raise ValueError("Doctor licence evidence differs from the generated sample PDF.")
        print(
            "Verified Dr. Tan: pending application with fictional sample licence PDF.", flush=True
        )
        return application["document_id"]
