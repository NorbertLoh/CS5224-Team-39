"""Render sample PDFs in the document service's own virtualenv."""

import argparse
import json
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--state", required=True, type=Path)
    args = parser.parse_args()
    sys.path.insert(0, str(args.root / "services/document"))
    from app.template_data import MedicalCertificate, Prescription, Receipt
    from app.templates import (
        render_medical_certificate,
        render_prescription,
        render_receipt,
    )

    types = {
        "prescription_pdf": (Prescription, render_prescription),
        "receipt_pdf": (Receipt, render_receipt),
        "medical_certificate_pdf": (MedicalCertificate, render_medical_certificate),
    }
    for spec in json.loads((args.state / "pdf-jobs.json").read_text(encoding="utf-8")):
        model, render = types[spec["kind"]]
        output = render(model.model_validate(spec["payload"]))
        (args.state / "pdfs" / f"{spec['document_id']}.pdf").write_bytes(output)
    print("Rendered clearly labelled demonstration PDFs.", flush=True)


if __name__ == "__main__":
    main()
