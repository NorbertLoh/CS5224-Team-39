"""A01-A03 live auth check. Synthetic local users only; never prints tokens."""

import base64
import hashlib
import os
import secrets
from html.parser import HTMLParser
from urllib.parse import parse_qs, urlsplit

import httpx


class Form(HTMLParser):
    def __init__(self):
        super().__init__()
        self.values = {}

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "input" and attrs.get("type") == "hidden":
            self.values[attrs["name"]] = attrs.get("value", "")


def main():
    endpoint = os.environ.get("AUTH_CHECK_ENDPOINT", "http://localhost:4566")
    if urlsplit(endpoint).hostname not in {"localhost", "127.0.0.1"}:
        raise SystemExit("This check is restricted to the local synthetic emulator.")
    client_id = os.environ["COGNITO_CLIENT_ID"]
    callback = os.environ.get("COGNITO_CALLBACK_URL", "http://localhost:5173/auth/callback")
    api = os.environ.get("AUTH_CHECK_API", "http://localhost:8000/auth/session")
    if urlsplit(api).hostname not in {"localhost", "127.0.0.1"}:
        raise SystemExit("The API probe is restricted to loopback.")
    logout_uri = os.environ.get("COGNITO_LOGOUT_URL", "http://localhost:5173/")
    oauth = endpoint + "/cognito-idp"
    for username in ("patient", "doctor", "clinic", "platform"):
        with httpx.Client(timeout=10, follow_redirects=False) as browser:
            verifier = secrets.token_urlsafe(32)
            challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
            params = dict(
                client_id=client_id,
                response_type="code",
                redirect_uri=callback,
                scope="openid email profile",
                state=secrets.token_urlsafe(32),
                code_challenge=challenge.decode().rstrip("="),
                code_challenge_method="S256",
            )
            response = browser.get(oauth + "/oauth2/authorize", params=params)
            assert response.status_code == 302, "Authorization did not redirect"
            login = browser.get(endpoint + response.headers["location"])
            form = Form()
            form.feed(login.text)
            response = browser.post(
                str(login.url),
                data={
                    **form.values,
                    "username": f"{username}@example.test",
                    "password": "LocalDemo123!",
                },
            )
            assert response.status_code == 302, "Synthetic login failed"
            query = parse_qs(urlsplit(response.headers["location"]).query)
            assert query["state"][0] == params["state"]
            redemption = dict(
                grant_type="authorization_code",
                client_id=client_id,
                redirect_uri=callback,
                code=query["code"][0],
                code_verifier=verifier,
            )
            response = browser.post(oauth + "/oauth2/token", data=redemption)
            response.raise_for_status()
            tokens = response.json()
            assert browser.post(oauth + "/oauth2/token", data=redemption).status_code == 400
            extra = browser.get(oauth + "/oauth2/authorize", params=params)
            extra_code = parse_qs(urlsplit(extra.headers["location"]).query)["code"][0]
            assert (
                browser.post(
                    oauth + "/oauth2/token",
                    data={
                        **redemption,
                        "code": extra_code,
                        "code_verifier": secrets.token_urlsafe(32),
                    },
                ).status_code
                == 400
            )
            assert (
                browser.post(
                    oauth + "/oauth2/token", data={**redemption, "code": extra_code}
                ).status_code
                == 400
            )
            access = tokens["access_token"]
            headers = {"Authorization": "Bearer " + access}
            probe = browser.get(api, headers=headers)
            assert probe.status_code == 200, "FastAPI rejected signed access token"
            if "id_token" in tokens:
                assert (
                    browser.get(
                        api, headers={"Authorization": "Bearer " + tokens["id_token"]}
                    ).status_code
                    == 401
                )
            refresh_body = {
                "ClientId": client_id,
                "AuthFlow": "REFRESH_TOKEN_AUTH",
                "AuthParameters": {"REFRESH_TOKEN": tokens["refresh_token"]},
            }
            cognito_headers = {
                "X-Amz-Target": "AWSCognitoIdentityProviderService.InitiateAuth",
                "Content-Type": "application/x-amz-json-1.1",
            }
            refreshed = browser.post(endpoint, json=refresh_body, headers=cognito_headers)
            refreshed.raise_for_status()
            refreshed_access = refreshed.json()["AuthenticationResult"]["AccessToken"]
            assert (
                browser.get(
                    api, headers={"Authorization": "Bearer " + refreshed_access}
                ).status_code
                == 200
            )
            # Pin the observed OAuth refresh limitation separately from the working SDK flow.
            oauth_refresh = browser.post(
                oauth + "/oauth2/token",
                data={
                    "grant_type": "refresh_token",
                    "client_id": client_id,
                    "refresh_token": tokens["refresh_token"],
                },
            )
            logout = browser.get(
                oauth + "/logout",
                params={"client_id": client_id, "logout_uri": logout_uri},
            )
            assert logout.status_code == 302
            next_login = browser.get(oauth + "/oauth2/authorize", params=params)
            assert "/cognito-idp/login" in next_login.headers["location"]
            revoked = browser.post(
                endpoint,
                json={"ClientId": client_id, "Token": tokens["refresh_token"]},
                headers={
                    **cognito_headers,
                    "X-Amz-Target": "AWSCognitoIdentityProviderService.RevokeToken",
                },
            )
            revoked.raise_for_status()
            assert (
                browser.post(endpoint, json=refresh_body, headers=cognito_headers).status_code
                == 400
            )
            print(
                f"{username}: PKCE, replay rejection, FastAPI access/ID split, refresh, "
                "hosted logout and revocation passed; "
                f"OAuth refresh HTTP {oauth_refresh.status_code}"
            )


if __name__ == "__main__":
    main()
