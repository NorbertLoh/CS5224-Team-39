import io
import json
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from botocore.exceptions import ClientError, EndpointConnectionError
from fastapi.testclient import TestClient
from telelink_common.auth import Principal, require_principal
from telelink_common.errors import DomainError

from app.database import get_session
from app.main import create_app
from app.services.demo_reset import KEY, ResetControl
from app.settings import Settings

CONFIG = {
    "deployment": "demo",
    "region": "ap-southeast-1",
    "bucket": "demo-reset",
    "cluster": "demo",
    "task": "fixed-reset-task:1",
    "network": {
        "awsvpcConfiguration": {
            "subnets": ["subnet-demo"],
            "securityGroups": ["sg-demo"],
            "assignPublicIp": "DISABLED",
        }
    },
}


class MemoryS3:
    exceptions = SimpleNamespace(NoSuchKey=type("NoSuchKey", (Exception,), {}))

    def __init__(self, state=None):
        self.state = state
        self.writes = 0
        self.conflict = False

    def get_object(self, **kwargs):
        assert kwargs == {"Bucket": "demo-reset", "Key": KEY}
        if self.state is None:
            raise self.exceptions.NoSuchKey()
        return {"Body": io.BytesIO(json.dumps(self.state).encode()), "ETag": str(self.writes)}

    def put_object(self, **kwargs):
        if self.conflict:
            raise ClientError({"Error": {"Code": "PreconditionFailed"}}, "PutObject")
        assert (
            kwargs.get("IfMatch") == str(self.writes)
            if self.state
            else kwargs["IfNoneMatch"] == "*"
        )
        self.state = json.loads(kwargs["Body"])
        self.writes += 1

    def close(self):
        pass


def service(state=None):
    s3, ecs = MemoryS3(state), Mock()
    ecs.run_task.return_value = {"tasks": [{"taskArn": "reset-task"}]}
    control = ResetControl(CONFIG)
    control.client = lambda name: {"s3": s3, "ecs": ecs}[name]
    return control, s3, ecs


def test_get_does_not_claim_or_launch():
    control, s3, ecs = service()
    assert control.status() == {"status": "ready"}
    assert s3.writes == 0
    ecs.run_task.assert_not_called()


def test_fixed_targets_and_idempotent_launch_retry():
    control, s3, ecs = service()
    request_id = str(uuid4())
    first = control.start(request_id, "operator")
    assert first["status"] == "queued"
    control.start(request_id, "operator")
    assert s3.writes == 1
    calls = ecs.run_task.call_args_list
    assert calls[0] == calls[1]
    assert calls[0].kwargs["taskDefinition"] == CONFIG["task"]
    assert calls[0].kwargs["clientToken"] == request_id
    assert "actor_id" not in first


def test_concurrent_claim_cannot_start_second_worker():
    control, s3, ecs = service()
    s3.conflict = True
    with pytest.raises(DomainError) as error:
        control.start(str(uuid4()), "operator")
    assert error.value.code == "reset_active"
    ecs.run_task.assert_not_called()


@pytest.mark.parametrize("status", ["queued", "running"])
def test_active_job_blocks_a_different_request(status):
    control, _, ecs = service({"request_id": "other", "status": status})
    with pytest.raises(DomainError):
        control.start(str(uuid4()), "operator")
    ecs.run_task.assert_not_called()


def test_ambiguous_launch_keeps_claim_for_same_token_retry():
    control, s3, ecs = service()
    ecs.run_task.side_effect = EndpointConnectionError(endpoint_url="https://ecs.example")
    with pytest.raises(DomainError):
        control.start(str(uuid4()), "operator")
    assert s3.state["status"] == "queued"
    assert s3.writes == 1


def test_running_replay_returns_status_without_launching():
    state = {
        "request_id": "same",
        "status": "running",
        "stage": "Restoring seed",
        "updated_at": "now",
    }
    control, s3, ecs = service(state)
    assert control.start("same", "operator") == state
    assert s3.writes == 0
    ecs.run_task.assert_not_called()


@pytest.fixture
def api(monkeypatch):
    app = create_app(Settings(_env_file=None, demo_reset_config=CONFIG))
    actor = SimpleNamespace(
        subject_id=uuid4(), email="platform@example.test", global_roles=["platform_admin"]
    )
    session = Mock()
    session.scalar.return_value = actor
    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[require_principal] = lambda: Principal("operator", frozenset())
    control, _, ecs = service()
    monkeypatch.setattr("app.api.demo_reset.ResetControl", lambda config: control)
    with TestClient(app) as client:
        yield client, app, actor, ecs


def test_page_status_is_authorized_and_read_only(api):
    client, _, _, ecs = api
    assert client.get("/demo-reset").json() == {"status": "ready"}
    ecs.run_task.assert_not_called()
    assert (
        client.post(
            "/demo-reset", json={"request_id": str(uuid4()), "confirmation": "RESET DEMO"}
        ).status_code
        == 202
    )


@pytest.mark.parametrize(
    "role,email,expected",
    [
        ("patient", "patient@example.test", 403),
        ("platform_admin", "another@example.test", 403),
    ],
)
def test_only_seeded_platform_operator_can_reset(api, role, email, expected):
    client, _, actor, ecs = api
    actor.global_roles, actor.email = [role], email
    for response in (
        client.get("/demo-reset"),
        client.post(
            "/demo-reset",
            json={
                "request_id": str(uuid4()),
                "confirmation": "RESET DEMO",
            },
        ),
    ):
        assert response.status_code == expected
    ecs.run_task.assert_not_called()


def test_disabled_operation_and_unauthenticated_requests(api):
    client, app, _, ecs = api
    app.state.settings.demo_reset_config = None
    assert client.get("/demo-reset").status_code == 404
    app.dependency_overrides.pop(require_principal)
    assert client.get("/demo-reset").status_code == 401
    ecs.run_task.assert_not_called()


@pytest.mark.parametrize(
    "extra", [{"confirmation": "reset"}, {"task": "untrusted"}, {"request_id": "bad"}]
)
def test_confirmation_uuid_and_target_injection_are_rejected(api, extra):
    client, _, _, ecs = api
    body = {"request_id": str(uuid4()), "confirmation": "RESET DEMO"} | extra
    assert client.post("/demo-reset", json=body).status_code == 422
    ecs.run_task.assert_not_called()
