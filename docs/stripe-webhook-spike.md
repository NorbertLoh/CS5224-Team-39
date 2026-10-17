# X04 Stripe raw-body webhook spike

Tracking: [issue #161](https://github.com/NorbertLoh/CS5224-Team-39/issues/161).

Scope: verify a sample raw-body callback using the official Stripe SDK. This
independent sample spike was requested after merging X03 tooling in PR #159.
X03's real Checkout/Connect commission verification remains blocked on clinic
onboarding in issue #158; this work does not complete that integration.

Status: sample verification implemented in PR #162, awaiting review/merge.
No application payment mutations, durable event deduplication or outbox
processing; those belong to B03/B04.

## Install and verify the sample

From the repository root, Python 3.10+:

```powershell
python -m venv .local/x04-venv
.local/x04-venv/Scripts/python.exe -m pip install -r services/billing/spike/requirements.lock.txt
.local/x04-venv/Scripts/python.exe -m pytest services/billing/spike -q
.local/x04-venv/Scripts/python.exe -m ruff check services/billing/spike
.local/x04-venv/Scripts/python.exe -m ruff format --check services/billing/spike
.local/x04-venv/Scripts/python.exe -m pip check
```

No API key, connected account, external service or database is needed. Tests
generate independent SHA-256 HMAC signatures over `timestamp.raw_body` using a
public synthetic secret; the official Stripe Python SDK 16.0.0 verifies them.
This proves the requested **sample raw-body callback** boundary, not a real
Stripe delivery or successful Checkout/Connect integration.

The loopback test starts an actual Uvicorn HTTP server on a temporary port and
sends raw UTF-8 JSON. It expects HTTP 200 for the original signed bytes, HTTP 400
for changed bytes and HTTP 400 for an expired signature, then stops its server.
The remaining checks exercise header/signature failures, JSON reserialization,
wrong secrets, multiple v1 signatures, malformed/live payloads, configuration,
size limits, future timestamps and repeated callbacks without payment processing.

## Run the isolated callback

```powershell
.local/x04-venv/Scripts/python.exe services/billing/spike/webhook.py --demo
```

This binds only `127.0.0.1:8014`; the only route is
`POST /stripe/webhook`. `--demo` uses an explicitly public synthetic secret.
Keep this isolated tool local. It is not a deployed billing webhook endpoint.

The handler reads bounded raw body chunks (256 KiB maximum), then calls
`stripe.Webhook.construct_event` with those exact bytes and a 300-second
timestamp tolerance. It does not parse or reserialize JSON before verification.
An additional check rejects timestamps more than 300 seconds in the future.
Invalid requests get a generic 400 response; oversized requests get 413.
Secrets, signature headers, payloads and provider exception details are not
logged. Successful responses include `mode: signature-spike` and
`payment_processed: false`. Repeats are acknowledged but not deduplicated.

This follows Stripe's [signature verification guidance](https://docs.stripe.com/events/manage-webhook-endpoints#signature-errors)
and the [official SDK verifier](https://github.com/stripe/stripe-python/blob/v16.0.0/stripe/_webhook.py).

## Optional real Stripe CLI delivery

Install the [Stripe CLI](https://docs.stripe.com/stripe-cli), authenticate to
the same sandbox, then run in another terminal:

```powershell
stripe listen --events payment_intent.succeeded --forward-to http://127.0.0.1:8014/stripe/webhook
```

Copy its `whsec_...` signing secret into `STRIPE_WEBHOOK_SECRET` in the ignored
`services/billing/.env`. The placeholder is also in `.env.example`.
Restart the callback **without** `--demo`, then trigger a test event:

```powershell
.local/x04-venv/Scripts/python.exe services/billing/spike/webhook.py
# In a separate terminal:
stripe trigger payment_intent.succeeded
```

Expect the CLI to report HTTP 200 for the forwarded test event. Use the CLI
listener's secret, not the API key or a Dashboard endpoint's signing secret.
Environment variables override `.env`. The CLI and Dashboard endpoints use
different secrets; never commit either. Only test snapshot events are accepted.
This optional delivery has not been run: the Stripe CLI is not installed locally.

## Evidence and limits

On 17 October 2026, Python 3.10.8 / Stripe SDK 16.0.0 passed **28 checks**,
including the real loopback HTTP callback. Ruff check/format and `pip check`
passed. The pinned test stack emits a Starlette warning about its httpx adapter;
all assertions, including actual socket transport, passed.

The dedicated X04 CI job installs the isolated lockfile and repeats these checks
without provider credentials. The main billing lockfile and runtime are unchanged.
X04 stays unchecked and issue #161 In progress until merge. Its sample criterion
does not establish Stripe-origin delivery, durable replay/deduplication, payment
state transitions, appointment confirmation or AWS routing. Those remain later
integration work; X03's onboarding blocker remains open.
