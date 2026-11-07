"""Submit and verify the requested local clinic application through the tenant API."""

import httpx
from requested_seed import SLUG, application


def clinic_application(cognito, client_id, password, phone, *, apply):
    auth = cognito.initiate_auth(
        ClientId=client_id,
        AuthFlow="USER_PASSWORD_AUTH",
        AuthParameters={"USERNAME": "clinic@example.test", "PASSWORD": password},
    )
    headers = {"Authorization": "Bearer " + auth["AuthenticationResult"]["AccessToken"]}
    expected = application(phone)
    with httpx.Client(timeout=30, trust_env=False, headers=headers) as http:
        if apply:
            response = http.post("http://tenant:8000/clinics", json=expected)
            response.raise_for_status()
        response = http.get("http://identity:8000/me")
        response.raise_for_status()
        matches = []
        for membership in response.json()["memberships"]:
            if membership["status"] != "active" or "clinic_admin" not in membership["roles"]:
                continue
            response = http.get("http://tenant:8000/clinics/" + membership["tenant_id"])
            response.raise_for_status()
            if response.json()["slug"] == SLUG:
                matches.append(response.json())
        if len(matches) != 1:
            raise ValueError("Expected one Meridian application owned by clinic@example.test.")
        clinic = matches[0]
        for key in ("name", "branding", "consultation_price"):
            if clinic[key] != expected[key]:
                raise ValueError(f"Clinic application {key} differs from the seed.")
        # Registration stays pending; never submit an approval/review action here.
        if clinic["status"] != "pending_review":
            raise ValueError(
                "The seeded clinic has already been reviewed; its decision was preserved."
            )
        response = http.get(f"http://tenant:8000/clinics/{clinic['tenant_id']}/location")
        response.raise_for_status()
        if response.json()["location"] != expected["location"]:
            raise ValueError("Clinic pickup details differ from the seed.")
        print(
            "Verified Meridian Health Partners application: pending review, SGD 30.00.", flush=True
        )
        return clinic["tenant_id"]
