"""Smoke-check one seeded patient against local Floci and FastAPI."""

import base64
import hashlib
import os
import re
import secrets
from urllib.parse import parse_qs, urlsplit

import httpx

FLOCI = "http://localhost:4566"
OAUTH = FLOCI + "/cognito-idp"
CALLBACK = "http://localhost:5173/auth/callback"
API = "http://localhost:8000/auth/session"


def cognito(client, action, **payload):
    response = client.post(FLOCI, json=payload, headers={
        "Content-Type": "application/x-amz-json-1.1",
        "X-Amz-Target": f"AWSCognitoIdentityProviderService.{action}",
    })
    response.raise_for_status()
    return response


def main():
    client_id = os.environ["COGNITO_CLIENT_ID"]
    verifier = secrets.token_urlsafe(32)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
    params = {
        "client_id": client_id, "response_type": "code", "redirect_uri": CALLBACK,
        "scope": "openid email profile", "state": secrets.token_urlsafe(32),
        "code_challenge": challenge.decode().rstrip("="), "code_challenge_method": "S256",
    }

    with httpx.Client(timeout=10) as client:
        # Open managed login and submit the seeded patient's credentials.
        login = client.get(OAUTH + "/oauth2/authorize", params=params, follow_redirects=True)
        login.raise_for_status()
        csrf = re.search(r'name="_csrf" value="([^"]+)"', login.text)
        assert csrf, "Login page did not contain a CSRF token"
        result = client.post(OAUTH + "/login", data={
            **params, "_csrf": csrf.group(1),
            "username": "patient@example.test", "password": "LocalDemo123!",
        })
        assert result.status_code == 302, "Patient login failed"
        callback = parse_qs(urlsplit(result.headers["location"]).query)
        assert callback["state"][0] == params["state"], "Login state did not match"

        # Exchange the code, then prove the access token works at the API.
        response = client.post(OAUTH + "/oauth2/token", data={
            "grant_type": "authorization_code", "client_id": client_id,
            "redirect_uri": CALLBACK, "code": callback["code"][0], "code_verifier": verifier,
        })
        response.raise_for_status()
        tokens = response.json()
        access = tokens["access_token"]
        client.get(API, headers={"Authorization": "Bearer " + access}).raise_for_status()

        # Floci 2.2.0 refreshes through the Cognito API, not OAuth refresh.
        response = cognito(client, "InitiateAuth", ClientId=client_id,
                           AuthFlow="REFRESH_TOKEN_AUTH",
                           AuthParameters={"REFRESH_TOKEN": tokens["refresh_token"]})
        access = response.json()["AuthenticationResult"]["AccessToken"]
        client.get(API, headers={"Authorization": "Bearer " + access}).raise_for_status()

        # Revoke this check's refresh token and clear its managed-login cookie.
        cognito(client, "RevokeToken", ClientId=client_id, Token=tokens["refresh_token"])
        logout = client.get(OAUTH + "/logout", params={
            "client_id": client_id, "logout_uri": "http://localhost:5173/",
        })
        assert logout.status_code == 302, "Hosted logout failed"
        assert logout.headers["location"] == "http://localhost:5173/"

    print("Patient login, API access, refresh and logout passed.")


if __name__ == "__main__":
    main()
