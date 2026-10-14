"""A11 real local HTTP check. Creates two synthetic clinics; never resets a database.

Uses the documented Floci accounts and Vite API proxy. Leaves the clinics suspended
for audit inspection. Requires the setup in docs/clinic-backend.md.
"""

from io import BytesIO
from uuid import uuid4

import httpx
from floci.check_auth import cognito, login
from PIL import Image

API = "http://localhost:5173/api/v1"


def request(client, method, path, token=None, status=200, **kwargs):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    response = client.request(method, API + path, headers=headers, **kwargs)
    assert response.status_code == status, (
        f"{method} {path}: expected {status}, got {response.status_code}"
    )
    return response.json() if response.content else None


def create_clinic(client, token, suffix):
    return request(
        client,
        "POST",
        "/tenant/clinics",
        token,
        status=201,
        json={
            "slug": f"a11-{suffix}",
            "name": f"A11 {suffix}",
            "branding": {
                "primary_color": "#156B63",
                "logo_url": None,
                "description": "Synthetic integration clinic.",
            },
            "consultation_price": {"amount_minor": 2500, "currency": "SGD"},
        },
    )


def check_clinic(client, tokens, clinic):
    admin, platform, doctor, patient = [
        tokens[role]["access_token"] for role in ["clinic", "platform", "doctor", "patient"]
    ]
    tenant_id = clinic["tenant_id"]
    path = f"/tenant/clinics/{tenant_id}"
    public = f"/tenant/clinics/by-slug/{clinic['slug']}"
    staff = f"/identity/clinics/{tenant_id}/memberships"
    request(client, "GET", public, status=404)
    request(client, "GET", path, patient, status=404)
    request(client, "GET", staff, patient, status=404)
    request(
        client,
        "POST",
        path + "/review",
        admin,
        status=403,
        json={"decision": "approve"},
    )
    request(
        client,
        "POST",
        path + "/review",
        platform,
        json={"decision": "reject", "reason": "Synthetic review check"},
    )
    request(client, "GET", public, status=404)
    request(client, "POST", path + "/review", platform, json={"decision": "approve"})
    saved = request(
        client,
        "PATCH",
        path,
        admin,
        json={
            "name": "A11 Persisted Clinic",
            "branding": {
                "primary_color": "#245678",
                "logo_url": None,
                "description": "Profile saved through the real frontend proxy.",
            },
            "consultation_price": {"amount_minor": 3210, "currency": "SGD"},
        },
    )
    profile = request(client, "GET", public)
    assert profile["name"] == saved["name"]
    assert profile["consultation_price"]["amount_minor"] == 3210
    assert profile["branding"]["primary_color"] == "#245678"
    request(
        client,
        "PUT",
        path + "/commission",
        admin,
        status=403,
        json={"commission_bps": 1250},
    )
    request(client, "PUT", path + "/commission", platform, json={"commission_bps": 1250})
    assert request(client, "GET", path, platform)["commission_bps"] == 1250
    assert "commission_bps" not in request(client, "GET", public)

    image = BytesIO()
    Image.new("RGB", (16, 16), "#245678").save(image, format="PNG")
    # Raw image upload uses the same path as the profile editor.
    response = client.put(
        API + path + "/logo",
        content=image.getvalue(),
        headers={"Authorization": f"Bearer {admin}", "Content-Type": "image/png"},
    )
    assert response.status_code == 200
    logo_url = request(client, "GET", public)["branding"]["logo_url"]
    assert logo_url
    # Local storefronts stream the private stored image through tenant's public route.
    response = client.get(API + path + "/public-logo")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    request(client, "DELETE", path + "/logo", admin)
    assert request(client, "GET", public)["branding"]["logo_url"] is None

    doctor_id = request(client, "GET", "/identity/me", doctor)["subject_id"]
    admin_id = request(client, "GET", "/identity/me", admin)["subject_id"]
    member = request(
        client,
        "POST",
        staff,
        admin,
        status=201,
        json={"email": "doctor@example.test", "roles": ["doctor"]},
    )
    assert member["subject_id"] == doctor_id
    assert any(
        item["doctor_id"] == doctor_id
        for item in request(client, "GET", path + "/doctors")["items"]
    )
    page = request(client, "GET", staff, admin, params={"limit": 1})
    assert len(page["items"]) == 1 and page["next_cursor"]
    next_page = request(
        client, "GET", staff, admin, params={"limit": 1, "cursor": page["next_cursor"]}
    )
    assert next_page["items"][0]["membership_id"] != page["items"][0]["membership_id"]
    request(client, "PUT", f"{staff}/{doctor_id}", admin, json={"roles": ["clinic_admin"]})
    assert not request(client, "GET", path + "/doctors")["items"]
    request(client, "PUT", f"{staff}/{doctor_id}", admin, json={"roles": ["doctor"]})
    request(client, "DELETE", f"{staff}/{admin_id}", admin, status=409)
    request(client, "DELETE", f"{staff}/{doctor_id}", admin, status=204)
    assert not request(client, "GET", path + "/doctors")["items"]
    assert not any(
        item["tenant_id"] == tenant_id
        for item in request(client, "GET", "/identity/me", doctor)["memberships"]
    )
    request(client, "PUT", f"{staff}/{doctor_id}", admin, json={"roles": ["doctor"]})
    assert request(client, "GET", path + "/doctors")["items"]
    request(client, "GET", staff, doctor, status=404)
    request(client, "PATCH", path, patient, status=404, json={"name": "Denied"})
    request(client, "GET", "/tenant/admin/clinics", patient, status=403)
    request(client, "GET", path, status=401)
    print("Profile, price, logo, commission, staff lifecycle, pagination and role denials passed.")


def main():
    tokens = {}
    clinics = []
    with httpx.Client(timeout=15) as client:
        pools = cognito(client, "ListUserPools", MaxResults=60).json()["UserPools"]
        pool = next(item["Id"] for item in pools if item["Name"] == "telelink-local")
        apps = cognito(client, "ListUserPoolClients", UserPoolId=pool, MaxResults=60)
        client_id = next(
            item["ClientId"]
            for item in apps.json()["UserPoolClients"]
            if item["ClientName"] == "telelink-web"
        )
        try:
            for role in ["clinic", "platform", "doctor", "patient"]:
                client.cookies.clear()
                tokens[role] = login(client, client_id, username=f"{role}@example.test")
            suffix = uuid4().hex[:12]
            clinic = create_clinic(client, tokens["clinic"]["access_token"], suffix)
            clinics.append(clinic)
            other = create_clinic(client, tokens["patient"]["access_token"], suffix + "-other")
            clinics.append(other)
            request(
                client,
                "GET",
                f"/tenant/clinics/{other['tenant_id']}",
                tokens["clinic"]["access_token"],
                status=404,
            )
            check_clinic(client, tokens, clinic)
            page = request(
                client,
                "GET",
                "/tenant/admin/clinics",
                tokens["platform"]["access_token"],
                params={"limit": 1},
            )
            assert page["next_cursor"]
            request(
                client,
                "GET",
                "/tenant/admin/clinics",
                tokens["platform"]["access_token"],
                params={"limit": 1, "cursor": page["next_cursor"]},
            )
        finally:
            for clinic in clinics:
                path = f"/tenant/clinics/{clinic['tenant_id']}"
                platform = tokens["platform"]["access_token"]
                profile = request(client, "GET", path, platform)
                if profile["status"] != "active":
                    request(
                        client,
                        "POST",
                        path + "/review",
                        platform,
                        json={"decision": "approve"},
                    )
                request(
                    client,
                    "POST",
                    path + "/review",
                    platform,
                    json={
                        "decision": "suspend",
                        "reason": "A11 synthetic check finished",
                    },
                )
                request(
                    client,
                    "GET",
                    f"/tenant/clinics/by-slug/{clinic['slug']}",
                    status=404,
                )
                request(client, "GET", path + "/doctors", status=404)
                print(f"Retained suspended synthetic clinic: {clinic['slug']}")
            for token in tokens.values():
                cognito(
                    client,
                    "RevokeToken",
                    ClientId=client_id,
                    Token=token["refresh_token"],
                )
    print("A11 real local integration passed; no AWS checks performed.")


if __name__ == "__main__":
    main()
