# RF58 AWS demo checkout configuration recovery

Issue #395 tracks the user-reported AWS checkout verification failure on
8 November 2026. This is an operational configuration repair with no application
code, schema or payment-state changes.

## Diagnosis

At 07:02:51 UTC the billing API route returned HTTP 503. Subsequent billing
reads returned HTTP 404 while scheduling reads returned HTTP 200. Authenticated
platform reads found one pending-payment appointment linked to a payment ID,
but no billing payment records. The appointment's clinic ID was absent from the
billing secret's `stripe_destinations` map, which retained two older clinic IDs.
The existing configured Stripe destination passed a read-only account lookup:
charges and payouts enabled, transfers active, country SG.

Consultation checkout reserves the scheduling payment reference before validating
the clinic's destination. Missing provider configuration can therefore leave a
reference with no billing payment row. The checkout UI intentionally reports an
unknown outcome instead of allowing another payment through a failed status read.

## Scoped repair and verification

Add the current authoritative demo clinic ID to the existing billing secret's
`stripe_destinations` JSON map using its already verified sandbox destination.
Preserve every existing secret field and mapping. Recreate the billing API and
worker tasks so both load the new version; changing Secrets Manager alone does
not refresh injected ECS settings. Verify completed deployments and healthy API
targets, then repeat authenticated read-only appointment/payment checks.

Do not submit a checkout, resend a webhook, change payment/appointment status or
create a replacement booking during diagnosis. Preserve the original request key
if an interrupted checkout is retried while its original hold is still valid.
After expiry, the old booking cannot be resumed. Confirm the original outcome
before making a fresh booking through the ordinary patient flow.

After a demo seed changes a clinic ID, verify its billing destination mapping
before beginning the payment journey. Automatic synchronization during reset is
a suggested follow-up, outside this configuration repair.

The current requested seed uses UUIDv5 with namespace URL and the constant
`telelink:requested-demo:meridian`. Independent calculation reproduces the live
clinic ID `ab6e2fe2-d436-5f73-b6ee-d9169f395400`. Repeating this same seed therefore
keeps the clinic ID. Once its mapping is added, subsequent resets using this
seed should retain that mapping because reset preserves provider configuration.
A different seed identity or manual secret replacement needs another check.
Reset still clears appointment/payment records and returns clinic/doctor
applications to pending approval.

## Current result

The diagnosis and read-only Stripe account checks passed. The existing key was
not exposed, and no checkout or payment was submitted. The interrupted booking's
original hold deadline was 07:12:43 UTC on 8 November 2026.

The runtime repair was blocked before execution by automatic approval review:
updating live Secrets Manager configuration and restarting billing services
requires explicit user authorization because of service-disruption and payment
impact risk. No secret update or service refresh was performed. Issue #395 stays
In progress and PR #396 stays draft pending approval and live verification.
The follow-up "ok will future reset break it again" was also rejected as
insufficiently explicit approval for the exact live mutation; both attempted
commands were blocked before execution.

A successful real checkout is outside this read-only verification and remains
an I05 acceptance check.
