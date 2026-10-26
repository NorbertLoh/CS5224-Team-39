from uuid import uuid4

import httpx
import pytest
from telelink_common.errors import DomainError

from app.integrations.tenant import TenantClient
from app.settings import Settings


def client_for(handler, **changes):
    return TenantClient(
        Settings(
            _env_file=None,
            environment="test",
            tenant_url="http://tenant.test",
            scheduling_secret="test-service-key-at-least-32-bytes-long",
            **changes,
        ),
        transport=httpx.MockTransport(handler),
    )


def test_directory_pagination():
    tenant_id, first, second = uuid4(), uuid4(), uuid4()
    calls = []

    def handler(request):
        calls.append(request.url.params.get("cursor"))
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "doctor_id": str(first if len(calls) == 1 else second),
                        "display_name": "Doctor",
                    }
                ],
                "next_cursor": "next-page" if len(calls) == 1 else None,
            },
        )

    client = client_for(handler)
    try:
        assert client.active_doctors(tenant_id, "test") == {first: "Doctor", second: "Doctor"}
        assert calls == [None, "next-page"]
    finally:
        client.close()


@pytest.mark.parametrize(
    "body",
    [
        {"items": [], "next_cursor": "loop"},
        {"items": [{"doctor_id": "invalid", "display_name": "Doctor"}], "next_cursor": None},
        {"items": [{"doctor_id": str(uuid4()), "display_name": ""}], "next_cursor": None},
    ],
)
def test_malformed_directory_fails_closed(body):
    client = client_for(lambda _: httpx.Response(200, json=body))
    try:
        with pytest.raises(DomainError) as error:
            client.active_doctors(uuid4(), "test")
        assert error.value.status_code == 502
    finally:
        client.close()


def test_directory_repeat_and_timeout():
    doctor_id = str(uuid4())
    client = client_for(
        lambda _: httpx.Response(
            200,
            json={
                "items": [{"doctor_id": doctor_id, "display_name": "Doctor"}],
                "next_cursor": "loop",
            },
        )
    )
    try:
        with pytest.raises(DomainError):
            client.active_doctors(uuid4(), "test")
    finally:
        client.close()

    def timeout(request):
        raise httpx.ReadTimeout("Test timeout", request=request)

    client = client_for(timeout)
    try:
        with pytest.raises(DomainError) as error:
            client.booking_profile(uuid4(), "test")
        assert error.value.status_code == 503
    finally:
        client.close()


def test_profile_context_and_money_validation():
    client = client_for(
        lambda _: httpx.Response(
            200,
            json={
                "tenant_id": str(uuid4()),
                "name": "Test Clinic",
                "status": "active",
                "consultation_price": {"amount_minor": 2500, "currency": "SGD"},
            },
        )
    )
    try:
        with pytest.raises(DomainError) as error:
            client.booking_profile(uuid4(), "test")
        assert error.value.status_code == 502
    finally:
        client.close()
