"""X04 loopback-only signature spike; never processes a payment."""

import argparse
import os
import time
from pathlib import Path

import stripe
from dotenv import dotenv_values
from fastapi import FastAPI, HTTPException, Request

TOLERANCE_SECONDS = 300
MAX_BODY_BYTES = 256 * 1024
DEMO_SECRET = "whsec_X04_SYNTHETIC_SAMPLE_ONLY"


def create_app(signing_secret: str) -> FastAPI:
    if not signing_secret.startswith("whsec_") or len(signing_secret) <= 6:
        raise ValueError("Configure a webhook signing secret (whsec_), not an API key")

    app = FastAPI(title="X04 signature spike", docs_url=None, redoc_url=None, openapi_url=None)

    @app.post("/stripe/webhook")
    async def webhook(request: Request):
        headers = request.headers.getlist("stripe-signature")
        if len(headers) != 1 or not headers[0]:
            raise HTTPException(400, "Invalid webhook")

        body = bytearray()
        async for chunk in request.stream():
            if len(body) + len(chunk) > MAX_BODY_BYTES:
                raise HTTPException(413, "Webhook too large")
            body.extend(chunk)

        try:
            # Never call request.json() or reserialize before authenticating these bytes.
            event = stripe.Webhook.construct_event(
                bytes(body), headers[0], signing_secret, tolerance=TOLERANCE_SECONDS
            ).to_dict()
            # SDK rejects old signatures; also bound timestamps ahead of the local clock.
            timestamp = int(
                next(part[2:] for part in headers[0].split(",") if part.startswith("t="))
            )
            if timestamp > time.time() + TOLERANCE_SECONDS:
                raise ValueError("Future signature")
            if (
                event.get("object") != "event"
                or event.get("livemode") is not False
                or not isinstance(event.get("id"), str)
                or not event["id"].startswith("evt_")
                or not isinstance(event.get("type"), str)
            ):
                raise ValueError("Not a test snapshot event")
        except (stripe.SignatureVerificationError, ValueError, TypeError, AttributeError):
            # No raw payload, header, endpoint secret or SDK exception text in responses/logs.
            raise HTTPException(400, "Invalid webhook") from None

        return {
            "accepted": True,
            "event_id": event["id"],
            "mode": "signature-spike",
            "payment_processed": False,
        }

    return app


def main():
    import uvicorn

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--demo", action="store_true", help="Use a public synthetic signing secret")
    parser.add_argument("--port", type=int, default=8014)
    args = parser.parse_args()
    config = dotenv_values(Path(__file__).resolve().parents[1] / ".env")
    secret = (
        DEMO_SECRET
        if args.demo
        else os.environ.get("STRIPE_WEBHOOK_SECRET", config.get("STRIPE_WEBHOOK_SECRET") or "")
    )
    try:
        app = create_app(secret)
    except ValueError as error:
        parser.error(str(error))
    if args.demo:
        print("X04 synthetic sample mode; no real Stripe delivery or payment processing.")
    uvicorn.run(app, host="127.0.0.1", port=args.port, access_log=False)


if __name__ == "__main__":
    main()
