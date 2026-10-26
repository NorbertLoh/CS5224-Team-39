import time

import httpx
import jwt
from telelink_common.access import ClinicMembership
from telelink_common.errors import DomainError


def provision_creator(client, settings, clinic, request_id):
    if client is None or settings.tenant_secret is None:
        raise DomainError(503, "unavailable", "Creator membership provisioning is not configured.")
    now = int(time.time())
    token = jwt.encode(
        {
            "iss": "telelink-service:tenant",
            "aud": "telelink-identity-provisioning",
            "sub": "tenant",
            "iat": now,
            "exp": now + 60,
        },
        settings.tenant_secret.get_secret_value(),
        algorithm="HS256",
    )
    try:
        response = client.put(
            "internal/clinic-creators",
            headers={"Authorization": "Bearer " + token, "X-Request-ID": request_id},
            json={"tenant_id": str(clinic.tenant_id), "subject_id": str(clinic.creator_subject_id)},
        )
        if response.status_code != 200:
            raise ValueError("Provisioning failed")
        membership = ClinicMembership.model_validate(response.json())
        if (
            membership.tenant_id != clinic.tenant_id
            or membership.subject_id != clinic.creator_subject_id
            or membership.status != "active"
            or "clinic_admin" not in membership.roles
        ):
            raise ValueError("Provisioning acknowledgement mismatch")
    except (httpx.RequestError, ValueError, TypeError):
        raise DomainError(
            503,
            "unavailable",
            "Creator membership provisioning failed; retry the same creation request.",
        ) from None
