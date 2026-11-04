# Upcoming demo slots and early video joining

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
# services/consultation/.env AND services/scheduling/.env
SERVICE_TEST_JOIN_EARLY_MINUTES=180
# apps/web/.env.local
VITE_LOCAL_TEST_JOIN_EARLY_MINUTES=180
```

Run the consultation migration from `services/consultation`, loading its existing
local database setting without displaying it:

```powershell
.venv/Scripts/python.exe -c "import os; from dotenv import dotenv_values; from alembic import command; from alembic.config import Config; os.environ['SERVICE_DATABASE_URL'] = dotenv_values('.env')['SERVICE_DATABASE_URL']; command.upgrade(Config('alembic.ini'), 'head')"
```

Restart consultation, scheduling and Vite after changing these settings.
All flags default to 10 minutes; supported values are integers from 10 to 180.
Backend settings reject an
extended window outside `local`/`test`. The frontend ignores its override in AWS
mode. Set all three to `10` (or remove them) and restart to restore ordinary behavior.
Keep these local files ignored; never use the override for deployed environments.

The backend enforces the configured window when issuing, consuming and checking
video admission. An extended local/test value above 10 also enables early clinical
start and completion, using that same window in both backend services. The default
10-minute video window still requires the scheduled time for clinical start.
Payment, identity, active participant membership, cancellation, completion, lease
expiry and the appointment end remain enforced. The setting does not move the
scheduled appointment, extend its end or permit overlapping slots.

Consultation migration `0003` adds a per-session bounded early-start allowance,
recorded only when starting the session. Actual clinical timestamps are preserved;
the recorded allowance is immutable after start. Ordinary sessions retain a zero
allowance. Downgrading refuses if early-start test sessions exist, rather than
rewriting their history. Keep migration `0003` for databases containing those sessions.
