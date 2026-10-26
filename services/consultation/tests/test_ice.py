import base64
import hashlib
import hmac
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.integrations.ice import configuration
from app.settings import Settings


def test_turn_credentials_are_bound_to_grant_peer_and_original_deadline():
    key = "v04-independent-turn-shared-secret-32-bytes"
    settings = Settings(
        _env_file=None,
        turn_urls=["turn:relay.test:3478?transport=tcp"],
        turn_secret=key,
        relay_only=True,
    )
    grant = {"expires_at": datetime(2026, 10, 18, tzinfo=timezone.utc), "peer_id": uuid4()}
    result = configuration(settings, grant)
    server = result["ice_servers"][0]
    assert server["username"] == f"1792281600:{grant['peer_id']}"
    assert (
        server["credential"]
        == base64.b64encode(
            hmac.new(key.encode(), server["username"].encode(), hashlib.sha1).digest()
        ).decode()
    )
    assert result["relay_only"] is True
    assert key not in str(result)
    assert configuration(Settings(_env_file=None), grant) == {
        "ice_servers": [],
        "relay_only": False,
    }


@pytest.mark.parametrize(
    "changes",
    [
        {"relay_only": True},
        {"turn_urls": ["turn:relay.test:3478"]},
        {"turn_secret": "x" * 32},
        {"turn_urls": ["https://relay.test"], "turn_secret": "x" * 32},
        {"turn_urls": ["turn:relay.test:3478"], "turn_secret": "short"},
    ],
)
def test_incomplete_or_invalid_turn_configuration_fails_startup(changes):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **changes)
