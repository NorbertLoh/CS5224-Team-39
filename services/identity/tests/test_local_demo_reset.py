from uuid import uuid4

import pytest
from pydantic import ValidationError
from telelink_common.errors import DomainError
from telelink_common.file_jobs import FileJobs
from test_demo_reset import api as api

from app.services.local_demo_reset import LocalResetControl
from app.settings import Settings


def test_local_claim_is_durable_idempotent_and_serialized(tmp_path):
    control = LocalResetControl(tmp_path)
    control.jobs.heartbeat()
    assert control.status() == {"status": "ready", "environment": "local"}
    request_id = str(uuid4())
    queued = control.start(request_id, "operator")
    assert queued["status"] == "queued" and "actor_id" not in queued
    assert LocalResetControl(tmp_path).start(request_id, "operator") == queued
    with pytest.raises(DomainError):
        control.start(str(uuid4()), "operator")
    state = control.jobs.read()
    with control.jobs.claim():
        control.jobs.update(state, "running", "Working")
        assert control.start(request_id, "operator")["status"] == "running"
        with pytest.raises(DomainError):
            control.start(str(uuid4()), "operator")
    control.jobs.update(state, "succeeded", "Done")
    assert control.start(str(uuid4()), "operator")["status"] == "queued"


def test_no_worker_means_no_new_job(tmp_path):
    control = LocalResetControl(tmp_path)
    with pytest.raises(DomainError):
        control.start(str(uuid4()), "operator")
    assert control.jobs.read() is None
    assert not (tmp_path / "claim").exists()


def test_atomic_write_does_not_leave_temporary_files(tmp_path):
    jobs = FileJobs(tmp_path)
    jobs.write({"status": "ready"})
    jobs.write({"status": "running"})
    assert jobs.read() == {"status": "running"}
    assert sorted(p.name for p in tmp_path.iterdir()) == ["state.json"]


@pytest.mark.parametrize("environment", ["demo", "production", "development"])
def test_local_reset_rejected_outside_local_test(environment, tmp_path):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, environment=environment, local_reset_state_dir=tmp_path)


def test_cannot_configure_both_targets(tmp_path):
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None, local_reset_state_dir=tmp_path, demo_reset_config={"deployment": "demo"}
        )


def test_local_api_uses_the_same_platform_guard_and_never_launches_aws(api, tmp_path):
    client, app, actor, ecs = api
    app.state.settings.demo_reset_config = None
    app.state.settings.local_reset_state_dir = tmp_path
    FileJobs(tmp_path).heartbeat()
    assert client.get("/demo-reset").json() == {"status": "ready", "environment": "local"}
    result = client.post(
        "/demo-reset", json={"request_id": str(uuid4()), "confirmation": "RESET DEMO"}
    )
    assert result.status_code == 202 and result.json()["environment"] == "local"
    actor.global_roles = ["patient"]
    assert client.get("/demo-reset").status_code == 403
    ecs.run_task.assert_not_called()
