"""Read the real host APIs to check the saved seed; never call payment/courier APIs."""

import json
from urllib.parse import urlsplit

import boto3
import httpx


def verify(ctx):
    manifest = json.loads((ctx.state / "manifest.json").read_text(encoding="utf-8"))
    jobs = json.loads((ctx.state / "pdf-jobs.json").read_text(encoding="utf-8"))
    cognito = boto3.client("cognito-idp", **ctx.aws_options)
    results = []
    headers = {}
    profiles = {}
    services = {
        "identity": 8001,
        "tenant": 8002,
        "scheduling": 8003,
        "consultation": 8004,
        "records": 8005,
        "fulfilment": 8006,
        "document": 8007,
        "billing": 8009,
    }
    with httpx.Client(timeout=30, trust_env=False) as client:
        for name, port in services.items():
            client.get(f"http://127.0.0.1:{port}/health/ready").raise_for_status()
            results.append(f"{name}: ready")
        client.get("http://127.0.0.1:5173/").raise_for_status()
        for account in manifest["accounts"]:
            auth = cognito.initiate_auth(
                AuthFlow="USER_PASSWORD_AUTH",
                ClientId=ctx.client_id,
                AuthParameters={
                    "USERNAME": account["email"],
                    "PASSWORD": "LocalDemo123!",
                },
            )
            key = account["email"].split("@")[0]
            headers[key] = {
                "Authorization": "Bearer " + auth["AuthenticationResult"]["AccessToken"]
            }
            response = client.get("http://127.0.0.1:8001/me", headers=headers[key])
            response.raise_for_status()
            profile = response.json()
            if (
                profile["subject_id"] != account["subject_id"]
                or profile["display_name"] != account["name"]
            ):
                raise ValueError("Seed account/profile mismatch.")
            profiles[key] = profile
            results.append(account["email"] + ": sign-in and profile verified")
        public = client.get("http://127.0.0.1:8002/clinics")
        public.raise_for_status()
        if len(public.json()["items"]) != 2:
            raise ValueError("Expected two public demo clinics.")
        platform = client.get("http://127.0.0.1:8002/admin/clinics", headers=headers["platform"])
        platform.raise_for_status()
        if len(platform.json()["items"]) != 5:
            raise ValueError("Expected five platform clinic examples.")
        for clinic in manifest["clinics"][:2]:
            cid = clinic["tenant_id"]
            logo = client.get(f"http://127.0.0.1:8002/clinics/{cid}/public-logo")
            logo.raise_for_status()
            if not logo.headers["content-type"].startswith("image/png"):
                raise ValueError("Clinic logo is not a PNG.")
            for url in [
                f"http://127.0.0.1:8001/clinics/{cid}/memberships",
                f"http://127.0.0.1:8003/appointments?tenant_id={cid}",
                f"http://127.0.0.1:8009/payments?tenant_id={cid}",
                f"http://127.0.0.1:8006/orders?tenant_id={cid}",
            ]:
                response = client.get(url, headers=headers["clinic"])
                response.raise_for_status()
                rows = response.json()["items"]
                if not rows or (
                    "memberships" not in url and any(row["tenant_id"] != cid for row in rows)
                ):
                    raise ValueError("Missing or incorrectly scoped clinic examples.")
            results.append(
                clinic["name"] + ": logo, staff, appointments, payments and orders verified"
            )
        for patient in ["patient", "patient2"]:
            for url in [
                "http://127.0.0.1:8003/appointments",
                "http://127.0.0.1:8005/api/v1/clinical-records/prescriptions",
                "http://127.0.0.1:8007/api/v1/document/documents",
                "http://127.0.0.1:8006/orders",
            ]:
                response = client.get(url, headers=headers[patient])
                response.raise_for_status()
                rows = response.json()["items"]
                if not rows:
                    raise ValueError("Patient examples are missing.")
                if "/document/" in url:
                    allowed = {
                        job["document_id"]
                        for job in jobs
                        if job["common"]["patient_id"] == profiles[patient]["subject_id"]
                    }
                    valid = all(row["document_id"] in allowed for row in rows)
                else:
                    valid = all(
                        row["patient_id"] == profiles[patient]["subject_id"] for row in rows
                    )
                if not valid:
                    raise ValueError("Patient examples are incorrectly scoped.")
            results.append(patient + ": appointments, prescriptions, documents and orders verified")
        docs = client.get(
            "http://127.0.0.1:8007/api/v1/document/documents",
            headers=headers["patient"],
        ).json()["items"]
        kinds = set()
        for document in docs:
            if document["kind"] in kinds:
                continue
            response = client.get(
                f"http://127.0.0.1:8007/api/v1/document/documents/{document['document_id']}/download",
                headers=headers["patient"],
            )
            response.raise_for_status()
            url = response.json()["download_url"]
            target = urlsplit(url)
            emulator = urlsplit(ctx.aws_endpoint)
            if (
                target.scheme != "http"
                or target.hostname not in {"localhost", "127.0.0.1"}
                or target.port != emulator.port
            ):
                raise ValueError("PDF verification requires the local emulator signer.")
            pdf = client.get(url)
            pdf.raise_for_status()
            if not pdf.content.startswith(b"%PDF"):
                raise ValueError("Downloaded document is not a PDF.")
            kinds.add(document["kind"])
        if kinds != {"prescription_pdf", "receipt_pdf", "medical_certificate_pdf"}:
            raise ValueError("Expected prescription, receipt and MC PDF examples.")
        denied = client.get(
            "http://127.0.0.1:8003/appointments",
            params={"tenant_id": manifest["clinics"][0]["tenant_id"]},
            headers=headers["clinic2"],
        )
        if denied.status_code not in {403, 404}:
            raise ValueError("Revoked clinic membership was not denied.")
        results.append("PDF downloads and revoked-clinic membership denial verified")
    (ctx.state / "verification.txt").write_text("\n".join(results) + "\n", encoding="utf-8")
    print("\n".join(results), flush=True)
