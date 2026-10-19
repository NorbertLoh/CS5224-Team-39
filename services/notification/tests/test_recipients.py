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
