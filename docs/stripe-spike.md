# X03 Stripe feasibility spike

Tracking: [issue #158](https://github.com/NorbertLoh/CS5224-Team-39/issues/158).

Status: complete in merged PRs #159/#164; issue #158 closed. The hosted test
payment and commission/transfer objects were verified on 18 October 2026.
Eight local unit tests and all eight inspection-fix push/PR CI checks passed.
Reproducing provider verification requires a platform test key and an onboarded
connected test account. Evidence and remaining integration limits are below.

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

Original gate before the 18 October retry: verify Connect readiness, complete a hosted
test payment, capture sanitized inspection evidence, and record decline/cancel
behaviour. Tooling merged in PR #159 at the requester's instruction; keep issue
#158 In progress and X03 unchecked until provider verification is complete. Access blockers belong
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

### Provider retry, 18 October 2026

The same connected SG account now reports `transfers: active` and
`charges_enabled: true`. The requester completed hosted Checkout in test mode.
Independent retrieval confirmed a completed/paid Session, succeeded PaymentIntent,
captured and unrefunded Charge, SGD 5 unrefunded application fee, and SGD 50
unreversed destination transfer. Clinic gross after the application fee is SGD 45;
Stripe processing fees reduce the platform's SGD 5 gross commission.

Sanitized provider identifiers (no customer/card data or Checkout URLs):

| Object | ID |
| --- | --- |
| Checkout Session | `cs_test_a10a9BuXFfe3pSXRg0AzJZfSCCbkkhN8HOZN2AMxjkaZ6pzMhCrTCsZeND` |
| PaymentIntent | `pi_3URoPDBTxJJFyMeS1S2aynCk` |
| Platform Charge | `ch_3URoPDBTxJJFyMeS1IZndt9n` |
| ApplicationFee | `fee_1URoPHBTxJcCTCXnvF73NVqT` |
| Transfer | `tr_3URoPDBTxJJFyMeS1cSRPGO7` |
| Destination payment | `py_1URoPGBTxJcCTCXnpmVlwPvy` |
| Connected account | `acct_1URoDIBTxJcCTCXn` |

The real response exposed an incorrect fixture assumption in the inspector:
for destination charges, the ApplicationFee's `originating_transaction` identifies
the platform Charge, while its `charge` identifies the Transfer's
`destination_payment`. Check both links rather than comparing `fee.charge` to the
platform Charge. References: [ApplicationFee](https://docs.stripe.com/api/application_fees/object)
and [Transfer](https://docs.stripe.com/api/transfers/object).

The corrected inspector returned `provider_verified: true` for this Session.
The earlier unpaid Session was rejected with `Missing or invalid payment_intents ID`.
Eight local unit tests passed, including rejection of mismatched/missing fee links.

Real declined/cancelled hosted payments have not been exercised. Fixture checks
reject unpaid/open/cancelled/failed states; these do not establish hosted decline
or cancellation behaviour. Application checkout/webhook integration remains
B02-B04. X04's completed sample-signature evidence and its current replacement
checks are in the [billing webhook guide](../services/billing/WEBHOOKS.md#retired-x04-standalone-receiver).
