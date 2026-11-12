"""Fictional, pending doctor application and clearly marked sample PDF evidence."""

from pathlib import Path

import httpx
from requested_seed import FIELDS, licence_pdf

PDF_PATH = Path("/state/output/pdf/dr-tan-demo-licence.pdf")


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
