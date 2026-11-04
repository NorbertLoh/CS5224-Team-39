import time
from types import SimpleNamespace

import jwt
import pytest
from pydantic import SecretStr

from telelink_common.errors import DomainError
from telelink_common.pagination import cursor_key, sign_cursor, verify_cursor

KEY = "cursor-signing-key-for-unit-checks-at-least-64-bytes-and-not-used-by-any-service"
ISSUER = "telelink-test-cursor"
AUDIENCE = "resource-list"


def verify(token, **changes):
    return verify_cursor(
        token,
        changes.get("key", KEY),
        issuer=changes.get("issuer", ISSUER),
        audience=changes.get("audience", AUDIENCE),
        required=["scope", "id"],
    )


def legacy_claims(**changes):
    now = int(time.time())
    return {
        "iss": ISSUER,
        "aud": AUDIENCE,
        "scope": ["patient", "created_at,id:desc"],
        "id": "resource-id",
        "iat": now,
        "exp": now + 900,
        **changes,
    }


def test_legacy_tokens_and_current_tokens_are_interoperable():
    claims = legacy_claims()
    legacy = jwt.encode(claims, KEY, algorithm="HS256")
    assert verify(legacy) == claims

    payload = {"scope": claims["scope"], "id": claims["id"], "status": None}
    token = sign_cursor(payload, KEY, issuer=ISSUER, audience=AUDIENCE)
    decoded = jwt.decode(
        token,
        KEY,
        algorithms=["HS256"],
        issuer=ISSUER,
        audience=AUDIENCE,
        options={"require": ["iat", "exp", "scope", "id"]},
    )
    assert decoded == verify(token)
    assert decoded["exp"] - decoded["iat"] == 900
    assert abs(decoded["iat"] - int(time.time())) <= 1
    assert decoded["scope"] == payload["scope"] and decoded["status"] is None
    assert payload == {"scope": claims["scope"], "id": claims["id"], "status": None}


@pytest.mark.parametrize("field", ["exp", "iat", "scope", "id"])
@pytest.mark.parametrize("missing", [True, False], ids=["missing", "null"])
def test_required_claims_remain_required(field, missing):
    claims = legacy_claims()
    if missing:
        del claims[field]
    else:
        claims[field] = None
    with pytest.raises(jwt.InvalidTokenError):
        verify(jwt.encode(claims, KEY, algorithm="HS256"))


@pytest.mark.parametrize(
    "changes",
    [
        {"exp": 0},
        {"iat": int(time.time()) + 3600},
        {"iss": "another-service"},
        {"aud": "another-list"},
    ],
)
def test_invalid_lifetime_or_recipient_is_rejected(changes):
    with pytest.raises(jwt.InvalidTokenError):
        verify(jwt.encode(legacy_claims(**changes), KEY, algorithm="HS256"))


@pytest.mark.parametrize("algorithm", ["HS384", "HS512"])
def test_only_hs256_is_accepted(algorithm):
    with pytest.raises(jwt.InvalidTokenError):
        verify(jwt.encode(legacy_claims(), KEY, algorithm=algorithm))


def test_wrong_key_tampering_and_malformed_tokens_are_rejected():
    token = sign_cursor({"scope": [], "id": "row"}, KEY, issuer=ISSUER, audience=AUDIENCE)
    with pytest.raises(jwt.InvalidTokenError):
        verify(token, key="another-key-at-least-32-bytes-for-checks")
    header, payload, signature = token.split(".")
    forged = ("A" if signature[0] != "A" else "B") + signature[1:]
    for candidate in (f"{header}.{payload}.{forged}", "not-a-token", ""):
        with pytest.raises(jwt.InvalidTokenError):
            verify(candidate)


def test_missing_cursor_configuration_preserves_service_error():
    with pytest.raises(DomainError) as error:
        cursor_key(SimpleNamespace(cursor_secret=None))
    assert error.value.status_code == 503
    assert cursor_key(SimpleNamespace(cursor_secret=SecretStr(KEY))) == KEY
