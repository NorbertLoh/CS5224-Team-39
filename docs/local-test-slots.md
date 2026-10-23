# Upcoming demo slots and early video joining

For stable demo browsing without a live-update websocket or automatic reloads,
run `powershell -ExecutionPolicy Bypass -File dev/local_stack.ps1 start -StableFrontend`.
The script builds and serves the frontend preview on the same port with the same
API proxies. The selected mode is remembered under ignored `.local/stack/` for
subsequent starts. Rerun start to rebuild after edits, then refresh manually.
To restore development mode, stop the stack, remove
`.local/stack/frontend-mode.txt`, then start normally.

Start the normal host stack first: `powershell -ExecutionPolicy Bypass -File dev/local_stack.ps1 start`.

Add upcoming 30-minute availability for `doctor@example.test` at the seeded
Harbour Family Clinic (`local-clinic`):

```powershell
services/identity/.venv/Scripts/python.exe dev/test_slots.py --hours 6
```

Rerun whenever fresh slots are needed. The helper fills the next six hours on
half-hour boundaries, leaving at least two minutes before the first slot.
`--hours 1` through `--hours 24` and `--clinic-slug <active-clinic-slug>` are
supported. The doctor must already belong to the clinic. The default uses the
existing demo clinic and its configured Stripe test destination; it does not
create another clinic or change memberships/payment configuration.

All calls target loopback services and local Floci demo authentication. Explicit
local service environments and a loopback Floci issuer are required. No database
reset or direct writes occur. Existing bookings/slots remain; API overlap
conflicts are skipped, including the doctor's slots at other clinics. A repeated
run does not create duplicates. Slots are availability, not paid appointments:
patients must still book and pay using the normal sandbox flow. This is an
on-demand command, not an automatic periodic worker.

To open video rooms up to three hours before their start, opt into both flags:

```dotenv
# services/consultation/.env
SERVICE_TEST_JOIN_EARLY_MINUTES=180
# apps/web/.env.local
VITE_LOCAL_TEST_JOIN_EARLY_MINUTES=180
```

Restart consultation and Vite after changing these settings. Both default to 10
minutes; supported values are integers from 10 to 180. Backend settings reject an
extended window outside `local`/`test`. The frontend ignores its override in AWS
mode. Set both to `10` (or remove them) and restart to restore ordinary behavior.
Keep these local files ignored; never use the override for deployed environments.

The backend enforces the configured window when issuing, consuming and checking
video admission. Payment, identity, active participant membership, cancellation,
completion, lease expiry and the appointment end remain enforced. This setting
opens video early; it does not move the scheduled start, extend the end, permit
overlapping slots, or allow starting/completing the clinical session early.
