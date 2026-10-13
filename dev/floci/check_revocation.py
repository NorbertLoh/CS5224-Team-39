"""Check that a revoked synthetic refresh token stays revoked across restart."""

import argparse
import json

import httpx
from botocore.exceptions import ClientError
from check_auth import login
from check_services import BASELINE, ENDPOINT, ROOT, aws

STATE = ROOT / ".local/f16-revocation.json"


def rejected(client_id, token):
    try:
        aws("cognito-idp").initiate_auth(ClientId=client_id, AuthFlow="REFRESH_TOKEN_AUTH",
                                       AuthParameters={"REFRESH_TOKEN": token})
    except ClientError as error:
        assert error.response["Error"]["Code"] == "NotAuthorizedException"
    else:
        raise AssertionError("Revoked refresh token was accepted after restart")


def prepare():
    if not BASELINE.is_file():
        raise SystemExit("Missing baseline. Run check_services.py prepare first.")
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    settings = baseline["cognito"]["client"]
    client_id = settings["ClientId"]
    with httpx.Client(timeout=10) as browser:
        tokens = login(browser, client_id, ENDPOINT + "/cognito-idp", settings["CallbackURLs"][0])
    refresh = tokens["refresh_token"]
    # Establish that this is a valid token before testing revocation.
    aws("cognito-idp").initiate_auth(ClientId=client_id, AuthFlow="REFRESH_TOKEN_AUTH",
                                   AuthParameters={"REFRESH_TOKEN": refresh})
    aws("cognito-idp").revoke_token(ClientId=client_id, Token=refresh)
    rejected(client_id, refresh)
    STATE.write_text(json.dumps({"client_id": client_id, "token": refresh}), encoding="utf-8")
    print("Synthetic token revoked and rejected; restart Floci, then run check.")


def check():
    if not STATE.is_file():
        raise SystemExit("Missing token file. Run check_revocation.py prepare before restarting Floci.")
    state = json.loads(STATE.read_text(encoding="utf-8"))
    rejected(state["client_id"], state["token"])
    print("Revocation survived restart.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "check"))
    args = parser.parse_args()
    if args.action == "prepare":
        prepare()
    else:
        check()
