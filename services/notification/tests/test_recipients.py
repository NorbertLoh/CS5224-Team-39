from uuid import uuid4

import httpx
import jwt
import pytest
from test_worker import workflow

from app.recipients import RecipientDirectory, RecipientLookupError
from app.settings import Settings


def settings(**changes):
    values = dict(
        _env_file=None,
        environment="test",
        email_sender="notifications@telelink.test",
        app_url="http://localhost:5173",
    )
    for name in ("identity", "scheduling", "document", "fulfilment"):
        values[name + "_url"] = f"http://{name}.test"
        values[name + "_secret"] = name + "-notification-test-secret-at-least-32-bytes"
    return Settings(**(values | changes))


@pytest.mark.parametrize(
    "kind", ["appointment_confirmed.v1", "document_ready.v1", "delivery_status_changed.v1"]
)
@pytest.mark.parametrize(
    "mutation",
    [None, "tenant", "resource", "recipient", "mailbox", "missing", "timeout", "redirect", "stale"],
)
def test_owner_context_and_current_mailbox(kind, mutation):
    event = workflow(kind)
    patient = uuid4()
    requests = []
    cfg = settings()

    def respond(request):
        service = request.url.host.split(".")[0]
        claims = jwt.decode(
            request.headers["Authorization"][7:],
            getattr(cfg, service + "_secret").get_secret_value(),
            algorithms=["HS256"],
            audience=f"telelink-{service}-notification",
        )
        assert claims["sub"] == "notification" and claims["exp"] - claims["iat"] == 60
        requests.append(request)
        if service == "identity":
            return httpx.Response(
                200,
                json={
                    "recipient_id": str(uuid4() if mutation == "recipient" else patient),
                    "email": "bad" if mutation == "mailbox" else "patient@example.test",
                },
            )
        if mutation == "missing":
            return httpx.Response(404)
        if mutation == "timeout":
            raise httpx.ReadTimeout("private upstream", request=request)
        if mutation == "redirect":
            return httpx.Response(302, headers={"Location": "http://other.test"})
        key = {
            "appointment_confirmed.v1": "appointment_id",
            "document_ready.v1": "document_id",
            "delivery_status_changed.v1": "delivery_id",
        }[kind]
        data = {
            "resource_id": str(uuid4() if mutation == "resource" else getattr(event.data, key)),
            "tenant_id": str(uuid4() if mutation == "tenant" else event.tenant_id),
            "patient_id": str(patient),
            "eligible": mutation != "stale",
        }
        for field in (
            "appointment_id",
            "prescription_id",
            "medical_certificate_id",
            "order_id",
            "status",
        ):
            value = getattr(event.data, field, None)
            data[field] = str(value) if value is not None else None
        assert request.url.params["tenant_id"] == str(event.tenant_id)
        return httpx.Response(200, json=data)

    directory = RecipientDirectory(cfg, transport=httpx.MockTransport(respond))
    try:
        if mutation in {None, "stale"}:
            result = directory.resolve(event)
            if mutation == "stale":
                assert result is None and len(requests) == 1
            else:
                assert result.subject_id == patient and result.email == "patient@example.test"
        else:
            with pytest.raises(RecipientLookupError) as error:
                directory.resolve(event)
            assert "private" not in str(error.value)
    finally:
        directory.close()


@pytest.mark.parametrize(
    "kind,field",
    [
        ("document_ready.v1", "prescription_id"),
        ("document_ready.v1", "appointment_id"),
        ("delivery_status_changed.v1", "order_id"),
    ],
)
def test_mismatched_source_links_are_rejected(kind, field):
    value = workflow(kind)

    def respond(request):
        key = "document_id" if kind == "document_ready.v1" else "delivery_id"
        data = value.data.model_dump(mode="json")
        data.update(
            resource_id=str(getattr(value.data, key)),
            tenant_id=str(value.tenant_id),
            patient_id=str(uuid4()),
            eligible=True,
        )
        data[field] = str(uuid4())
        return httpx.Response(200, json=data)

    directory = RecipientDirectory(settings(), transport=httpx.MockTransport(respond))
    try:
        with pytest.raises(RecipientLookupError):
            directory.resolve(value)
    finally:
        directory.close()


def test_stale_delivery_status_skips_mailbox_lookup():
    value = workflow("delivery_status_changed.v1")

    def respond(request):
        assert request.url.host == "fulfilment.test"
        return httpx.Response(
            200,
            json=dict(
                resource_id=str(value.data.delivery_id),
                tenant_id=str(value.tenant_id),
                patient_id=str(uuid4()),
                order_id=str(value.data.order_id),
                status="delivered",
                eligible=True,
            ),
        )

    directory = RecipientDirectory(settings(), transport=httpx.MockTransport(respond))
    try:
        assert directory.resolve(value) is None
    finally:
        directory.close()
