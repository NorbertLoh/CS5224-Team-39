from uuid import uuid4

import httpx
import pytest
from telelink_common.errors import DomainError

from app.settings import Settings
from app.upstream import RecordsUpstream


@pytest.mark.parametrize(
    "status,expected", [(401, 401), (403, 404), (404, 404), (429, 502), (302, 502), (500, 503)]
)
def test_appointment_failure_is_safe(status, expected):
    settings = Settings(_env_file=None, scheduling_url="http://scheduling")
    upstream = RecordsUpstream(
        settings,
        transport=httpx.MockTransport(
            lambda request: httpx.Response(status, json={"secret": "upstream-private-data"})
        ),
    )
    try:
        with pytest.raises(DomainError) as error:
            upstream.appointment(uuid4(), "token", "correlation")
        assert error.value.status_code == expected
        assert "upstream-private-data" not in error.value.detail
    finally:
        upstream.close()


@pytest.mark.parametrize(
    "case", ["wrong_id", "invalid_status", "malformed", "timeout", "unconfigured"]
)
def test_appointment_invalid_or_missing_upstream_fails_closed(case):
    appointment_id = uuid4()

    def respond(request):
        if case == "timeout":
            raise httpx.ReadTimeout("private provider details")
        if case == "malformed":
            return httpx.Response(200, content="not json")
        return httpx.Response(
            200,
            json={
                "appointment_id": str(uuid4() if case == "wrong_id" else appointment_id),
                "tenant_id": str(uuid4()),
                "patient_id": str(uuid4()),
                "doctor_id": str(uuid4()),
                "status": "unknown" if case == "invalid_status" else "in_progress",
            },
        )

    upstream = RecordsUpstream(
        Settings(
            _env_file=None, scheduling_url=None if case == "unconfigured" else "http://scheduling"
        ),
        transport=httpx.MockTransport(respond),
    )
    try:
        with pytest.raises(DomainError) as error:
            upstream.appointment(appointment_id, "token", "correlation")
        assert error.value.status_code == (503 if case in {"timeout", "unconfigured"} else 502)
    finally:
        upstream.close()


@pytest.mark.parametrize("case", ["wrong_tenant", "blank_name", "cycle", "second_page"])
def test_catalogue_context_and_pagination(case):
    tenant, medication = uuid4(), uuid4()
    calls = []

    def respond(request):
        calls.append(request)
        assert request.headers["Authorization"] == "Bearer doctor-token"
        assert request.headers["X-Request-ID"] == "request-id"
        item = {
            "medication_id": str(medication),
            "tenant_id": str(tenant),
            "display_name": "Synthetic",
            "active": True,
        }
        if case == "wrong_tenant":
            item["tenant_id"] = str(uuid4())
        if case == "blank_name":
            item["display_name"] = " "
        if case in {"cycle", "second_page"} and len(calls) == 1:
            return httpx.Response(200, json={"items": [], "next_cursor": "next"})
        if case == "cycle":
            return httpx.Response(200, json={"items": [], "next_cursor": "next"})
        return httpx.Response(200, json={"items": [item], "next_cursor": None})

    upstream = RecordsUpstream(
        Settings(_env_file=None, fulfilment_url="http://fulfilment"),
        transport=httpx.MockTransport(respond),
    )
    try:
        if case == "second_page":
            assert upstream.medications(tenant, {medication}, "doctor-token", "request-id") == {
                medication: "Synthetic"
            }
            assert calls[1].url.params["cursor"] == "next"
        else:
            with pytest.raises(DomainError) as error:
                upstream.medications(tenant, {medication}, "doctor-token", "request-id")
            assert error.value.status_code == 502
    finally:
        upstream.close()


@pytest.mark.parametrize(
    "field,value",
    [
        ("scheduling_url", "http://example.com"),
        ("fulfilment_url", "https://user:password@example.com"),
        ("fulfilment_url", "https://example.com?token=private"),
        ("cursor_secret", "short"),
    ],
)
def test_nonlocal_configuration_rejects_unsafe_values(field, value):
    with pytest.raises(ValueError):
        Settings(_env_file=None, environment="demo", **{field: value})
