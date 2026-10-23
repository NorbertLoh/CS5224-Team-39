# Repeatable Stripe sandbox refund demo

The regular demo seed creates simulated payment history. For a refundable example,
use this separate helper after seeding. It uses the running local services and real
Stripe test Checkout, without inserting payment rows or changing provider states.
It requires the host stack, synthetic demo accounts, an active clinic with a Stripe
test destination, and an available doctor slot within seven days. Keep the Stripe
forwarder and billing/scheduling workers running (`dev/local_stack.ps1 status`).

From the repository root, using the identity virtualenv's existing httpx and dotenv:

```powershell
services/identity/.venv/Scripts/python.exe dev/refund_demo.py prepare
```

Choose a particular clinic with `prepare --tenant <tenant-id>`. Otherwise the first
configured Stripe destination is used. The output includes clinic name, appointment,
payment, amount, hosted Checkout URL and payment deadline. Open the **complete** URL,
including its fragment. Pay within the hold deadline using Stripe's synthetic Visa
`4242 4242 4242 4242`, any future expiry and three-digit CVC, a synthetic name and
`patient@example.test`. This creates test transactions only; never enter a real card.
The amount comes from the clinic's current consultation price.

Wait for the signed callbacks and real workers to confirm the booking:

```powershell
services/identity/.venv/Scripts/python.exe dev/refund_demo.py status --expect paid
services/identity/.venv/Scripts/python.exe dev/refund_demo.py cancel
services/identity/.venv/Scripts/python.exe dev/refund_demo.py status --expect refundable
```

Sign in as `clinic@example.test`, then **Manage clinic → select the named clinic →
Payments → latest consultation → Payment details → Refund payment**. Enter a reason
and confirm the full amount. The backend and worker perform the Stripe test refund;
wait for refund success and scheduling synchronization:

```powershell
services/identity/.venv/Scripts/python.exe dev/refund_demo.py status --expect refunded
```

Rerunning `prepare` resumes the saved example; it does not automatically charge,
cancel or refund it. `cancel` affects only that saved, successfully paid appointment.
The helper never requests a refund; clinic admins trigger it from the application.
After a full refund, use `prepare --new` to start another example. An expired unpaid
example may be replaced once its payment is failed, or if checkout was never created.
An unresolved payment blocks replacement, including late paid bookings.

Generated IDs, idempotency key and Checkout URL stay in ignored
`.local/refund-demo.json`; no tokens or provider secrets are written there.
`--root <configured-checkout>` supports running the helper from another worktree.
After a full seed reset, the saved example refers to removed records; remove this
small local state file before preparing another. Normal seed resets never create
Stripe transactions or refund existing Stripe charges.

## Local example prepared on 23 October 2026

Hosted Stripe sandbox Checkout paid SGD 35 for Harbour Family Clinic (Demo).
Actual signed callbacks and billing/event/scheduling workers confirmed appointment
`c2c54dd5-c517-453e-b669-c41cba517a83`, linked to payment
`85070cd1-a298-4734-85c4-db65c9cbb8ba`. The clinic cancellation API then produced
`cancelled` / `refund_required`, with the succeeded payment reporting refund
availability `available` and no refund attempts. Rerunning `prepare` reused the same
booking and payment. This example is left ready for the user to refund in Payments;
full multi-service refund completion is not claimed by this run.
