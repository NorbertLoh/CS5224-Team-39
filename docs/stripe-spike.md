# X03 Stripe feasibility spike

Tracking: [issue #158](https://github.com/NorbertLoh/CS5224-Team-39/issues/158).

Status: in progress. Real Stripe test Checkout, Connect access and commission
verification require a platform test key and an onboarded connected test account.
No provider verification has been completed yet; X03 remains unchecked.

Scope is an isolated feasibility tool and reproducible evidence for B02/X04.
Application checkout APIs and webhook verification belong to those later tasks.

## Configuration

Python 3.10+ is sufficient; the standalone CLI uses only the standard library.
Fill the ignored `services/billing/.env` (placeholders created locally):

```dotenv
STRIPE_SECRET_KEY=sk_test_REPLACE_LOCALLY
STRIPE_CONNECTED_ACCOUNT_ID=acct_REPLACE_LOCALLY
```

Use a **platform** test secret key and a connected account in that same sandbox.
Enable Connect and finish the connected account's test onboarding with synthetic
details until its `transfers` capability is active. Follow Stripe's
[Connect testing guide](https://docs.stripe.com/connect/testing).
The tool does not create accounts or change onboarding settings. Country,
cross-border and platform restrictions must be verified for the actual sandbox;
this spike assumes a same-region destination and does not set `on_behalf_of`.

Environment variables override the file. `--env-file PATH` selects another file;
there is no shell evaluation, and only the two Stripe names are loaded.
Only `sk_test_` keys are accepted. Requests target `api.stripe.com` over HTTPS,
refuse redirects and pin [API version 2024-06-20](https://docs.stripe.com/changelog/2024-06-20).
No credentials, raw provider responses, customer details or card data are logged.
The create command prints a sensitive hosted Checkout URL: open it locally and
do not commit it. HTTP errors report only their status; inspect test Dashboard
API logs for the precise account/capability restriction.

## Real provider verification

From `services/billing`:

```powershell
python scripts/stripe_spike.py account
python scripts/stripe_spike.py create --run-id x03-attempt-001
# Open the returned checkout_url in your browser and finish the test payment.
python scripts/stripe_spike.py inspect --session-id cs_test_REPLACE
```

Reuse a run ID only to retry the same create request; use a fresh ID for a new
attempt. The idempotency key includes the destination account. This creates a
fixed synthetic SGD 50 consultation with a SGD 5 application fee. Per Stripe's
[destination-charge guide](https://docs.stripe.com/connect/destination-charges?platform=web&ui=stripe-hosted),
the platform creates the charge and transfers the full amount to the connected
account; the application fee returns to the platform. Stripe processing fees
reduce platform net, so SGD 5 is gross commission, while clinic gross is SGD 45.

Use Stripe's success test card `4242 4242 4242 4242`, a future expiry and any CVC
with synthetic contact details. The same guide lists `4000 0000 0000 9995` for
decline testing. Confirm the hosted page displays test mode before paying.
Cancel or decline must never yield successful inspection evidence.

The return URLs point to localhost port 5173 for convenience and do not require
the app to run. A failed localhost redirect does not invalidate a completed
Stripe test payment. The tool has no return handler; retrieve the original
session ID to inspect payment status.

Inspection separately retrieves the Session, PaymentIntent, Charge,
ApplicationFee and Transfer. It checks test mode, completed/paid/succeeded states,
capture/refund/reversal state, linkage, destination, currency and exact amounts.
Save only the sanitized inspection JSON and account readiness result as review
evidence. The result confirms provider feasibility at inspection time; it does
not confirm an appointment or implement application payment truth.
X04 must still verify raw-body webhooks; B02-B04 own application integration.

## Offline adapter and checks

```powershell
python scripts/stripe_spike.py demo
python -m unittest discover -s tests -p test_stripe_spike.py -v
```

`demo` returns a fixed synthetic split labelled `demo-fixture`, with
`provider_verified: false` and `task_complete: false`. It creates no provider
objects or usable Checkout URL. It is an isolated demonstration adapter only.
It must not be wired in as a successful billing integration.
The existing billing CI also collects the spike tests through pytest.

## Evidence and remaining gate

On 17 October 2026, the seven standalone unit tests and the offline demo passed
on Python 3.10.8. Missing credentials fail before network access; the local `.env`
is ignored by Git. These checks use fixtures and do not prove provider access.

Pending: fill both local variables, verify Connect readiness, complete a hosted
test payment, capture sanitized inspection evidence, and record decline/cancel
behaviour. Keep issue #158 In progress, PR #159 draft and X03 unchecked until
provider verification is complete and the PR is merged. Access blockers belong
on the issue; do not unblock B02 with offline fixture evidence.

Provider check on 17 October 2026: both local variables are now configured.
The platform test key successfully retrieved the connected SG account. Its
`transfers` and `card_payments` capabilities were `inactive`, with
`details_submitted: false` and `requirements.disabled_reason: requirements.past_due`.
Missing requirements include the business profile, test representative details,
external account and terms acceptance. A real test Checkout creation attempt was
rejected with HTTP 400 / `insufficient_capabilities_for_transfer`; no Checkout URL
or completed payment was produced. Finish the clinic's sandbox onboarding before
retrying. All PR checks passed, including billing PostgreSQL tests and Ruff.
