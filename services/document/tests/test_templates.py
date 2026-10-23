from datetime import date, datetime, timezone
from io import BytesIO

import pytest
from pydantic import ValidationError
from pypdf import PdfReader

from app.template_data import (
    MedicalCertificate,
    Prescription,
    PrescriptionItem,
    Receipt,
    ReceiptItem,
)
from app.templates import render_medical_certificate, render_prescription, render_receipt

HEADER = {
    "clinic_name": "Synthetic Clinic & Care",
    "clinic_address": "123 Synthetic Street\nSingapore 123456",
    "patient_name": "Synthetic Patient",
    "reference": "DEMO-001",
    "issued_at": datetime(2026, 10, 15, 2, 30, tzinfo=timezone.utc),
}
DOCTOR = {"doctor_name": "Dr Synthetic", "doctor_registration": "DEMO-MCR-001"}
ITEM = PrescriptionItem(display_name="Synthetic medication", quantity=2, instructions="Demo only")


def prescription(**overrides):
    return Prescription(**(HEADER | DOCTOR | {"items": (ITEM,)} | overrides))


def receipt(**overrides):
    return Receipt(
        **(
            HEADER
            | {
                "payment_reference": "DEMO-PAYMENT-001",
                "paid_at": HEADER["issued_at"],
                "items": (ReceiptItem(description="Consultation", amount_minor=2505),),
                "total_minor": 2505,
            }
            | overrides
        )
    )


def mc(**overrides):
    return MedicalCertificate(
        **(
            HEADER
            | DOCTOR
            | {
                "consultation_date": date(2026, 10, 15),
                "unfit_from": date(2026, 10, 15),
                "unfit_through": date(2026, 10, 16),
            }
            | overrides
        )
    )


@pytest.mark.parametrize(
    "render,data,expected",
    [
        (render_prescription, prescription(), ["Prescription", "Quantity: 2", "Demo only"]),
        (render_receipt, receipt(), ["Receipt", "SGD 25.05", "DEMO-PAYMENT-001"]),
        (render_medical_certificate, mc(), ["Medical Certificate", "16 Oct 2026", "2 day(s)"]),
    ],
)
def test_rendered_pdf_content(render, data, expected):
    payload = render(data)
    assert payload.startswith(b"%PDF-")
    reader = PdfReader(BytesIO(payload))
    assert len(reader.pages) == 1
    text = reader.pages[0].extract_text()
    for value in [*expected, "Synthetic Patient", "15 Oct 2026, 10:30 SGT", "Page 1"]:
        assert value in text
    assert reader.metadata.title in ["Prescription", "Receipt", "Medical Certificate"]
    assert "Synthetic Patient" not in str(reader.metadata)


def test_escape_markup_and_supported_unicode():
    text = (
        PdfReader(BytesIO(render_prescription(prescription(patient_name="René <b>A&B</b>"))))
        .pages[0]
        .extract_text()
    )
    assert "René <b>A&B</b>" in text


def test_unsupported_glyph_fails_explicitly():
    with pytest.raises(ValueError, match="unsupported"):
        render_prescription(prescription(patient_name="患者"))


def test_long_instructions_paginate_without_losing_last_item():
    items = tuple(
        PrescriptionItem(
            display_name=f"Synthetic medication {number}",
            quantity=1,
            instructions="Long synthetic instruction & text. " * 50,
        )
        for number in range(20)
    )
    reader = PdfReader(BytesIO(render_prescription(prescription(items=items))))
    assert len(reader.pages) > 1
    assert "Synthetic medication 19" in "\n".join(page.extract_text() for page in reader.pages)
    for number, page in enumerate(reader.pages, 1):
        assert f"Page {number}" in page.extract_text()


@pytest.mark.parametrize(
    "factory,overrides",
    [
        (prescription, {"items": ()}),
        (prescription, {"clinic_name": "  "}),
        (prescription, {"issued_at": datetime(2026, 10, 15)}),
        (receipt, {"total_minor": 1}),
        (receipt, {"currency": "USD"}),
        (receipt, {"paid_at": datetime(2026, 10, 16, tzinfo=timezone.utc)}),
        (receipt, {"total_minor": 25.05}),
        (mc, {"unfit_through": date(2026, 10, 14)}),
    ],
)
def test_invalid_snapshots_fail(factory, overrides):
    with pytest.raises(ValidationError):
        factory(**overrides)


def test_single_day_mc():
    text = PdfReader(BytesIO(render_medical_certificate(mc(unfit_through=date(2026, 10, 15)))))
    assert "1 day(s)" in text.pages[0].extract_text()


def test_single_very_long_instruction_splits_across_pages():
    item = PrescriptionItem(
        display_name="Long directions sample",
        quantity=1,
        instructions=("Sample instruction. " * 900) + "FINAL DIRECTIONS",
    )
    reader = PdfReader(BytesIO(render_prescription(prescription(items=(item,)))))
    assert len(reader.pages) > 1
    assert "FINAL DIRECTIONS" in "\n".join(page.extract_text() for page in reader.pages)
    for page in reader.pages:
        assert "Medicine and directions" in page.extract_text()


def test_long_receipt_and_mc_content_is_preserved():
    items = tuple(
        ReceiptItem(description=f"Sample charge {number}: " + "description " * 12, amount_minor=100)
        for number in range(100)
    )
    receipt_reader = PdfReader(BytesIO(render_receipt(receipt(items=items, total_minor=10000))))
    assert len(receipt_reader.pages) > 1
    assert "Sample charge 99" in "\n".join(page.extract_text() for page in receipt_reader.pages)
    assert "SGD 100.00" in receipt_reader.pages[-1].extract_text()
    certificate = mc(
        patient_name="Long sample name " * 10,
        additional_notes="Sample notes only. " * 800 + "FINAL NOTE",
    )
    mc_reader = PdfReader(BytesIO(render_medical_certificate(certificate)))
    assert len(mc_reader.pages) > 1
    assert "FINAL NOTE" in "\n".join(page.extract_text() for page in mc_reader.pages)
    assert "Dr Synthetic" in mc_reader.pages[-1].extract_text()


@pytest.mark.parametrize(
    "render,data",
    [
        (render_prescription, prescription(doctor_registration=None, clinic_address=None)),
        (render_medical_certificate, mc(doctor_registration=None, clinic_address=None)),
    ],
)
def test_optional_fields_do_not_create_placeholder_credentials(render, data):
    text = "\n".join(page.extract_text() for page in PdfReader(BytesIO(render(data))).pages)
    assert "Dr Synthetic" in text
    assert "Medical registration" not in text
    assert "Signature" not in text
