"""Render synthetic RF02 review PDFs; never connects to services or storage."""

import argparse
from datetime import date, datetime, timezone
from pathlib import Path

from app.rendering.template_data import (
    MedicalCertificate,
    Prescription,
    PrescriptionItem,
    Receipt,
    ReceiptItem,
)
from app.rendering.templates import render_medical_certificate, render_prescription, render_receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    header = {
        "clinic_name": "TeleLink Demonstration Clinic [SAMPLE]",
        "clinic_address": "Sample address for layout review\nSingapore - demonstration only",
        "patient_name": "Alex Tan [SAMPLE PATIENT]",
        "issued_at": datetime(2026, 10, 23, 2, 30, tzinfo=timezone.utc),
    }
    doctor = {"doctor_name": "Dr Sample Clinician"}
    samples = {
        "prescription.pdf": render_prescription(
            Prescription(
                **header,
                **doctor,
                reference="SAMPLE-RX-2026-001",
                items=(
                    PrescriptionItem(
                        display_name="Demonstration tablet A (sample only)",
                        quantity=12,
                        instructions=(
                            "Sample directions for layout review only. Not for clinical use."
                        ),
                    ),
                    PrescriptionItem(
                        display_name="Demonstration preparation B (sample only)",
                        quantity=1,
                        instructions="Sample dispensing instructions. Not a real prescription.",
                    ),
                ),
            )
        ),
        "receipt.pdf": render_receipt(
            Receipt(
                **header,
                reference="SAMPLE-RCPT-2026-001",
                payment_reference="SAMPLE-PAYMENT-001",
                paid_at=header["issued_at"],
                items=(
                    ReceiptItem(description="Consultation (sample)", amount_minor=3500),
                    ReceiptItem(description="Prescribed medicines (sample)", amount_minor=1200),
                    ReceiptItem(description="Delivery (sample)", amount_minor=800),
                ),
                total_minor=5500,
            )
        ),
        "medical-certificate.pdf": render_medical_certificate(
            MedicalCertificate(
                **header,
                **doctor,
                reference="SAMPLE-MC-2026-001",
                consultation_date=date(2026, 10, 23),
                unfit_from=date(2026, 10, 23),
                unfit_through=date(2026, 10, 25),
                additional_notes=(
                    "Sample document for layout review only. "
                    "Not valid for medical or absence certification."
                ),
            )
        ),
    }
    for name, payload in samples.items():
        (args.output / name).write_bytes(payload)
        print(f"Rendered {name}")


if __name__ == "__main__":
    main()
