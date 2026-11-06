"""Link the demo doctor through clinic-owned staff APIs without changing verification."""

import httpx
from clinic_application import SLUG


def doctor_membership(cognito, client_id, password, *, apply):
    auth = cognito.initiate_auth(
        ClientId=client_id,
        AuthFlow="USER_PASSWORD_AUTH",
        AuthParameters={"USERNAME": "clinic@example.test", "PASSWORD": password},
    )
    headers = {"Authorization": "Bearer " + auth["AuthenticationResult"]["AccessToken"]}
    with httpx.Client(timeout=30, trust_env=False, headers=headers) as http:
        response = http.get("http://identity:8000/me")
        response.raise_for_status()
        clinics = []
        for membership in response.json()["memberships"]:
            if membership["status"] != "active" or "clinic_admin" not in membership["roles"]:
                continue
            response = http.get("http://tenant:8000/clinics/" + membership["tenant_id"])
            response.raise_for_status()
            if response.json()["slug"] == SLUG:
                clinics.append(response.json()["tenant_id"])
        if len(clinics) != 1:
            raise ValueError("Expected one Meridian clinic owned by clinic@example.test.")
        tenant_id = clinics[0]
        url = f"http://identity:8000/clinics/{tenant_id}/memberships"
        if apply:
            response = http.post(url, json={"email": "doctor@example.test", "roles": ["doctor"]})
            response.raise_for_status()
        cursor = None
        matches = []
        while True:
            params = {"limit": 100}
            if cursor:
                params["cursor"] = cursor
            response = http.get(url, params=params)
            response.raise_for_status()
            page = response.json()
            matches.extend(
                item for item in page["items"] if item["subject"]["email"] == "doctor@example.test"
            )
            cursor = page["next_cursor"]
            if not cursor:
                break
        if (
            len(matches) != 1
            or matches[0]["status"] != "active"
            or matches[0]["roles"] != ["doctor"]
        ):
            raise ValueError("Expected one active Dr. Tan doctor assignment to Meridian.")
        print(
            "Verified Dr. Tan assigned to Meridian as doctor; verification: "
            + matches[0]["subject"]["doctor_verification"],
            flush=True,
        )
        return matches[0]["membership_id"]
