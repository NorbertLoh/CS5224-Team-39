"""Short-lived coturn REST credentials, issued only after successful admission."""

import base64
import hashlib
import hmac


def configuration(settings, grant):
    if not settings.turn_urls:
        return {"ice_servers": [], "relay_only": False}
    username = f"{int(grant['expires_at'].timestamp())}:{grant['peer_id']}"
    credential = base64.b64encode(
        hmac.new(
            settings.turn_secret.get_secret_value().encode(), username.encode(), hashlib.sha1
        ).digest()
    ).decode()
    return {
        "ice_servers": [
            {"urls": settings.turn_urls, "username": username, "credential": credential}
        ],
        "relay_only": settings.relay_only,
    }
