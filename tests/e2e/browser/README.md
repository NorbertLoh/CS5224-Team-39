# Portable deployment E2E checks (I05)

Run these tests from your laptop or CI against the public application origin. The
same tests support local and AWS staging ingress; they never connect to PostgreSQL,
edit business rows, inject payment webhooks or invent courier statuses. Application
APIs and normal browser sign-in enforce the real role and tenant checks.

Issue [#323](https://github.com/NorbertLoh/CS5224-Team-39/issues/323), draft
PR [#324](https://github.com/NorbertLoh/CS5224-Team-39/pull/324). I05 remains **In
progress** until deployment dependencies and the genuine AWS journey are complete.

## Install and configure

Requires Node 22.12+ (24 used for verification) and pnpm 11.25.0. From this directory:

```powershell
npm install --global pnpm@11.25.0
pnpm install --frozen-lockfile --ignore-scripts
pnpm install:browser
Copy-Item .env.example .env
```

On a fresh Linux runner, use `pnpm exec playwright install --with-deps chromium`.
Fill the ignored `.env` with the public origin and dedicated synthetic accounts.
Do not use real patient accounts/data. There are no implicit target, account or
password defaults. Missing required configuration fails the selected test rather
than skipping it.

- `E2E_TARGET=local` accepts HTTPS or loopback HTTP. Local self-signed HTTPS requires
  explicitly setting `E2E_IGNORE_HTTPS_ERRORS=true`.
- `E2E_TARGET=aws-staging` requires a deployed HTTPS origin and valid TLS. Set
  `E2E_IGNORE_HTTPS_ERRORS=false`. Supply the public CloudFront/custom-domain URL,
  not an internal ALB, ECS address or direct backend port.
- `E2E_API_PATH` defaults to `/api/v1`; requests use same-origin public ingress.
  Deploy the frontend to use that same API prefix. Split-origin APIs are not
  supported by this initial suite.
- The four accounts must already exist and support the app's email/password login.
  Confirm their email and set permanent passwords. Complete doctor review and
  assign both doctor and clinic admin to `E2E_CLINIC_SLUG`, an existing active test
  clinic. Approval alone does not grant clinic membership.
- AWS Cognito app-client/password-auth configuration and API Gateway token scopes
  must support the same login method as the deployed UI. The suite does not bypass
  authentication or substitute emulator tokens. Hosted PKCE/MFA acceptance remains
  a separate check.

Use `.env.local`/`.env.aws` if keeping both configurations, and select one explicitly:

```powershell
node --env-file=.env.aws node_modules/playwright/cli.js test --project=smoke
```

Environment variables take precedence over files. A target name is a declaration,
not proof of the destination's identity: supply the correct dedicated staging URL.

## Runs and pass criteria

```powershell
pnpm test:unit       # Configuration validation; no deployment required
pnpm test           # Read-only smoke: public clinic + all four roles
pnpm test:booking   # One real unpaid booking and release; requires write opt-in
pnpm test:stripe    # Headed browser, manual hosted TEST payment handoff
pnpm test:evidence  # Read-only assertions against a retained completed journey
pnpm report        # Open the latest HTML report
```

Each invocation writes its own latest report. Copy `playwright-report/` and
`test-results/` elsewhere before the next run if retaining all runs. JUnit and JSON
results are in `test-results/`; failures include screenshots. Resource ID
attachments record created appointment/slot/payment IDs and cleanup outcome.
No automatic retries recreate bookings or provider operations.

| Run | Acceptance established by a pass |
| --- | --- |
| Smoke | Directory and active storefront load; approved doctors appear; all four roles sign in and call their real APIs. Patient profile, appointments, prescriptions, documents, orders and payments; doctor appointments/availability; clinic settings/orders/payments; platform review queues are reachable. |
| Booking | Assigned doctor creates a future slot through public API; patient chooses it in the UI and creates a correctly priced hold; UI releases it; public availability shows the slot available again; cleanup withdraws the created slot. |
| Stripe | Browser creates a hold and opens a genuine `cs_test_` hosted Checkout; operator completes payment; public application APIs eventually show succeeded payment and confirmed appointment; doctor sees confirmation and patient confirmation UI agrees. |
| Evidence | The supplied completed visit and order match patient/clinic/prescription; distinct consultation and medication/delivery payments succeeded with matching totals/quote; medicine is ready; tracking reaches the explicitly expected status; matching prescription PDF becomes ready and its presigned download returns PDF bytes. |

A smoke pass is **not** a claim that the complete patient journey works. The
evidence run verifies existing state and object download, not new event delivery or
the steps that created those records. Record when/how the supplied journey was
performed and which deployment/version produced it; rerun it on AWS to establish
AWS behavior. Never use seeded/fabricated paid rows as provider integration evidence.

## Unpaid booking run

Set `E2E_ALLOW_WRITES=true`, then run `pnpm test:booking`. It creates a random
half-hour slot 3–8 days ahead for the configured doctor. Use dedicated accounts so
this does not collide with shared demo work. A real overlap fails rather than
modifying someone else's slot. It does not initiate checkout, charge, prescribe,
mark medicines ready or submit a courier request.

Cleanup cancels only the unpaid hold created by this run and withdraws its slot
through authorised APIs. The cancelled appointment/audit history stays intact. A
cleanup error fails the run. If a request outcome is uncertain, inspect the attached
IDs and the doctor's schedule before removal; the suite does not guess, reset the
database or retry writes. An interrupted process cannot guarantee cleanup.

## Genuine Stripe payment handoff

Configure the backend with Stripe **test-mode** credentials and the clinic's test
connected account, then explicitly set both `E2E_ALLOW_WRITES=true` and
`E2E_STRIPE_TEST_MODE=true`. Run `pnpm test:stripe` on a desktop with a display.

The browser automates booking and opening Checkout. When instructed in the
terminal, complete the visible test payment with `4242 4242 4242 4242`, any future
expiry and a three-digit CVC. It waits up to `E2E_PAYMENT_WAIT_SECONDS` (default
480; the booking hold remains the server's original ten-minute deadline), then
allows up to two minutes for actual asynchronous confirmation. Do not close the
browser during the handoff. The suite requires a `cs_test_` Checkout URL and never
automates CAPTCHA or changes a payment outcome.

Stripe documents security measures that prevent reliable hosted UI automation:
[automated testing](https://docs.stripe.com/automated-testing). This is deliberately
an interactive provider acceptance check, not an unattended CI payment test.

Locally, keep the Stripe CLI forwarder and payment/event workers running. On AWS,
configure the real publicly reachable Stripe test webhook endpoint and signing
secret, and run the deployed billing/scheduling publishers/consumers. Do not use a
local forwarder to hide a broken AWS callback endpoint. Returning from Checkout
alone cannot pass: the test verifies persisted payment and booking state through
the public APIs, including amount and ownership.

Paid or pending-payment records are retained for audit and subsequent consultation;
no automatic refund or paid cancellation is attempted. Check attached IDs before
rerunning; a rerun intentionally creates a new booking.

## Documents, medication and tracking evidence

After completing a genuine synthetic consultation/medicine journey, set:

```dotenv
E2E_APPOINTMENT_ID=<completed-appointment-UUID>
E2E_ORDER_ID=<matching-paid-medicine-order-UUID>
E2E_EXPECT_DELIVERY_STATUS=submitted
```

Run `pnpm test:evidence`. It never advances the consultation, changes prices,
charges, marks medicines ready or updates Lalamove. Before running, the doctor
must complete the clinical workflow, clinic admin price every medicine, patient
confirm recipient/address and pay, and admin mark medicines ready. Configure the
clinic's saved pickup/contact, supported destination postcode, provider sandbox
credentials and deployed delivery/document/event workers. See
[current pricing](../../../docs/medication-pricing.md),
[checkout contacts](../../../docs/RF14-checkout-contacts.md) and
[I03](../../../docs/I03-local-journey.md).

For Lalamove, the application currently polls verified provider responses. Check
real sandbox acceptance with `submitted`. After a genuine sandbox cancellation,
use `cancelled`; cancellation does not establish delivery or a refund. The suite
will wait for the deployed tracker to observe the requested status. Use
`picked_up`/`delivered` only when that status actually exists at the provider.
No provider lifecycle simulator is added by this change. Controlled adapter tests
remain separate from provider integration acceptance; see
[tracking](../../../services/fulfilment/TRACKING.md).

## AWS manual workflow

After this PR is merged, GitHub Actions → **Deployment E2E** → **Run workflow** runs
the unattended smoke suite, optionally followed by booking/release. It does not
deploy AWS or perform a hosted Stripe payment. The URL comes from environment
configuration rather than free-form dispatch input to avoid sending credentials
to an accidentally supplied destination.

Pushes/PRs run configuration tests and test discovery only, with no credentials or
deployment access. Only an explicit workflow dispatch runs against staging.

Create GitHub environment `e2e-staging` with these environment **variables**:
`E2E_BASE_URL` (public HTTPS origin), `E2E_CLINIC_SLUG` (dedicated active clinic).
Add these eight environment **secrets**:

```text
E2E_PATIENT_EMAIL             E2E_PATIENT_PASSWORD
E2E_DOCTOR_EMAIL              E2E_DOCTOR_PASSWORD
E2E_CLINIC_ADMIN_EMAIL        E2E_CLINIC_ADMIN_PASSWORD
E2E_PLATFORM_ADMIN_EMAIL      E2E_PLATFORM_ADMIN_PASSWORD
```

The workflow requires valid TLS, uses one worker, serializes staging runs and
uploads each run's report separately with three-day retention. It does not alter
AWS resources or require AWS credentials. Restrict the environment and artifact
access to your team. Reports/screenshots can contain synthetic account/contact
details and error diagnostics; keep them private. Traces/video are disabled to
avoid routinely recording auth/network credentials. Reports and `.env` files are
gitignored.

## Verification and remaining acceptance

4 November 2026, local public `https://localhost:8443`, real running Compose
services and documented synthetic accounts: **6 configuration checks, all 5
browser smoke checks, and 1 booking/release check passed**. The booking test
confirmed reavailability and withdrew its synthetic slot through the API. No
Stripe payment, clinical completion, courier request or AWS deployment was made
for this verification. Stripe and evidence tests are executable but not exercised
in this run. GitHub workflow dispatch awaits staging/environment configuration.

Still required for full I05/Q04/Q05 acceptance:

- A fresh genuine AWS paid → consultation → prescription → pricing → paid
  medicines → ready → sandbox dispatch journey (W11/W20 dependencies pending).
- Browser automation of clinic/doctor onboarding, clinical completion, medication
  pricing and checkout; these remain manual in the initial preparatory suite.
- Real two-network audio/video and forced TURN checks, with human media quality
  confirmation; same-machine browser connectivity cannot establish this.
- Actual notification arrival in a controlled mailbox (including deployed SES),
  MC/receipt content checks and the remaining authorisation/negative tests.

Do not check off I05 based on these local preparatory results.
