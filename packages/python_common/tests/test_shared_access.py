from copy import deepcopy
from types import SimpleNamespace
from uuid import UUID

import httpx
import pytest
from pydantic import ValidationError

from telelink_common.access import IdentityClient, has_tenant_role
from telelink_common.errors import DomainError
from telelink_common.settings import ServiceSettings

SUBJECT = "00000000-0000-4000-8000-000000000003"
TENANT = "00000000-0000-4000-8000-000000000002"


def identity_payload():
    return {
        "subject_id": SUBJECT,
        "cognito_sub": "verified-runtime-sub",
        "display_name": "Synthetic",
        "global_roles": ["patient"],
        "memberships": [
            {
                "membership_id": "00000000-0000-4000-8000-000000000005",
                "subject_id": SUBJECT,
                "tenant_id": TENANT,
                "roles": ["clinic_admin"],
                "status": "active",
                "created_at": "2026-10-13T01:00:00.000Z",
                "updated_at": "2026-10-13T01:00:00.000Z",
            }
        ],
    }


def test_tenant_role_requires_matching_active_membership_and_explicit_platform_override():
    membership = SimpleNamespace(tenant_id=UUID(TENANT), roles=["clinic_admin"], status="active")
    assert has_tenant_role(membership, UUID(TENANT), "clinic_admin")
    assert not has_tenant_role(membership, UUID(SUBJECT), "clinic_admin")
    assert not has_tenant_role(membership, UUID(TENANT), "doctor")
    membership.status = "revoked"
    assert not has_tenant_role(membership, UUID(TENANT), "clinic_admin")
    assert not has_tenant_role(None, UUID(TENANT), "doctor", global_roles=["platform_admin"])
    assert has_tenant_role(
        None,
        UUID(TENANT),
        "clinic_admin",
        global_roles=["platform_admin"],
        allow_platform_admin=True,
    )


def test_lookup_forwards_only_verified_token_and_correlation_and_checks_current_response():
    requests = []
    payload = identity_payload()

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json=payload)

    settings = ServiceSettings(_env_file=None, identity_url="http://identity.test/api/v1/identity")
    client = IdentityClient(settings, transport=httpx.MockTransport(handler))
    try:
        assert (
            client.current_identity("token", "verified-runtime-sub", "request-01")
            .memberships[0]
            .status
            == "active"
        )
        payload["memberships"][0]["status"] = "revoked"
        assert (
            client.current_identity("token", "verified-runtime-sub", "request-02")
            .memberships[0]
            .status
            == "revoked"
        )
        assert len(requests) == 2
        assert str(requests[0].url) == "http://identity.test/api/v1/identity/me"
        assert requests[0].headers["authorization"] == "Bearer token"
        assert requests[0].headers["x-request-id"] == "request-01"
        assert "x-user-id" not in requests[0].headers
    finally:
        client.close()


@pytest.mark.parametrize(
    "change",
    [
        "wrong_sub",
        "wrong_membership_subject",
        "duplicate_tenant",
        "invalid_role",
        "duplicate_role",
        "missing_timestamp",
        "naive_timestamp",
        "duplicate_global_role",
    ],
)
def test_invalid_identity_responses_fail_closed(change):
    payload = identity_payload()
    if change == "wrong_sub":
        payload["cognito_sub"] = "other-user"
    elif change == "wrong_membership_subject":
        payload["memberships"][0]["subject_id"] = TENANT
    elif change == "duplicate_tenant":
        payload["memberships"].append(deepcopy(payload["memberships"][0]))
    elif change == "invalid_role":
        payload["memberships"][0]["roles"] = ["platform_admin"]
    elif change == "duplicate_role":
        payload["memberships"][0]["roles"] = ["doctor", "doctor"]
    elif change == "missing_timestamp":
        del payload["memberships"][0]["created_at"]
    elif change == "naive_timestamp":
        payload["memberships"][0]["created_at"] = "2026-10-13T01:00:00"
    else:
        payload["global_roles"] = ["patient", "patient"]
    client = IdentityClient(
        ServiceSettings(_env_file=None, identity_url="http://identity.test"),
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload)),
    )
    try:
        with pytest.raises(DomainError) as error:
            client.current_identity("token", "verified-runtime-sub", "request-01")
        assert error.value.status_code == 502
        assert error.value.code == "upstream_error"
    finally:
        client.close()


@pytest.mark.parametrize(
    "status, expected", [(401, 401), (403, 403), (500, 503), (503, 503), (404, 502), (302, 502)]
)
def test_upstream_errors_are_safe_and_redirects_are_not_followed(status, expected):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(
            status, text="private-secret", headers={"Location": "https://attacker.test"}
        )

    client = IdentityClient(
        ServiceSettings(_env_file=None, identity_url="http://identity.test"),
        transport=httpx.MockTransport(handler),
    )
    try:
        with pytest.raises(DomainError) as error:
            client.current_identity("token", "verified-runtime-sub", "request-01")
        assert error.value.status_code == expected
        assert "private-secret" not in error.value.detail
        assert len(calls) == 1
    finally:
        client.close()


def test_missing_identity_configuration_and_timeout_fail_closed():
    client = IdentityClient(ServiceSettings(_env_file=None, identity_url=None))
    with pytest.raises(DomainError) as error:
        client.current_identity("token", "sub", "id")
    assert error.value.status_code == 503

    def timeout(request):
        raise httpx.ReadTimeout("private-host", request=request)

    client = IdentityClient(
        ServiceSettings(_env_file=None, identity_url="http://identity.test"),
        transport=httpx.MockTransport(timeout),
    )
    try:
        with pytest.raises(DomainError) as error:
            client.current_identity("token", "sub", "id")
        assert error.value.status_code == 503
        assert "private-host" not in error.value.detail
    finally:
        client.close()


@pytest.mark.parametrize(
    "url",
    [
        "http://identity.test",
        "https://user:secret@identity.test",
        "https://identity.test?token=secret",
    ],
)
def test_nonlocal_identity_url_configuration_requires_tls_without_credentials(url):
    with pytest.raises(ValidationError):
        ServiceSettings(_env_file=None, environment="production", identity_url=url)
