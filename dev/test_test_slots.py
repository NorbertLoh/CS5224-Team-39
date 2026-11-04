from datetime import datetime, timedelta, timezone

import httpx
import pytest
from test_slots import candidates, generate


def test_stable_candidates_and_minimum_lead():
    now = datetime(2030, 1, 1, 10, 29, 59, tzinfo=timezone.utc)
    slots = list(candidates(now, 6))
    assert slots[0] == now.replace(hour=11, minute=0, second=0)
    assert all(start >= now + timedelta(minutes=2) for start in slots)
    assert all(
        start + timedelta(minutes=30) <= now + timedelta(hours=6) for start in slots
    )
    assert set(slots).issubset(candidates(now + timedelta(seconds=1), 6))


def test_nonlocal_environment_rejected_before_network(tmp_path):
    def unexpected(request):
        pytest.fail("A nonlocal configuration must not make network calls")

    with (
        httpx.Client(transport=httpx.MockTransport(unexpected)) as client,
        pytest.raises(ValueError, match="local service environments"),
    ):
        generate(tmp_path, "local-clinic", 6, client)


def test_remote_issuer_rejected_before_authentication(tmp_path):
    for name in ("identity", "tenant", "scheduling"):
        directory = tmp_path / "services" / name
        directory.mkdir(parents=True)
        (directory / ".env").write_text(
            "SERVICE_ENVIRONMENT=local\nSERVICE_AUTH_ISSUER=https://remote.example/pool\n"
        )
    with (
        httpx.Client(
            transport=httpx.MockTransport(
                lambda request: pytest.fail("Unexpected network")
            )
        ) as client,
        pytest.raises(ValueError, match="local Floci"),
    ):
        generate(tmp_path, "local-clinic", 6, client)
