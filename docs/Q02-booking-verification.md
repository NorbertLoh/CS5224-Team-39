# Q02: competing bookings and hold expiry

Start the real local identity, tenant and scheduling services described in
[the I01 setup](I01-local-journey.md), including Floci, PostgreSQL on `55411`,
Redis and the scheduling expiry worker. Use an active demo clinic with
`doctor@example.test` as a member. The checker uses `patient@example.test` and
`clinic@example.test`, which have distinct identities and the patient role.
Install scheduling's locked dependencies and the shared Python package first.

From the repository root in PowerShell:

```powershell
services/scheduling/.venv/Scripts/python.exe tests/e2e/check_q02_booking.py --tenant-id <active-clinic-UUID>
```

Allow about ten minutes. For a separate source checkout, add
`--config-root <configured-checkout>`. The checker accepts only local Floci,
local Redis and the persistent development database on `55411`.
It creates one future slot and uses real authenticated HTTP requests. Its SQL
connection enforces read-only transactions, and Redis is only read. It waits for
the original server deadline without changing persisted timestamps or clocks.

On 21 October 2026 (Singapore time), all ten checks passed:

- Two distinct authenticated patients raced for one slot: one received `201`,
  the other `409`.
- PostgreSQL contained exactly one active reservation, and Redis identified it.
- A repeated request returned `409` without extending the original deadline.
- Withdrawing the reserved slot returned `409`.
- After the unchanged 600-second deadline elapsed, the other patient booked the
  slot successfully. The original appointment was persisted as `expired`.
- The replacement belonged to that other patient, with exactly one active
  reservation and the corresponding Redis mirror.

Run `1d7fa9792a8b49cebb1e5868df631eeb` completed with cleanup successful.
Evidence is written to `.local/q02/<run-id>.json`, without credentials or tokens.
Cleanup cancels its remaining hold, withdraws its own slot and revokes acquired
refresh tokens. It attempts each resource independently and records failures;
an interrupted or failed run needs its report checked before rerunning.
Historical appointment rows remain as audit evidence.

The confirmation invariant is additionally covered by existing scheduling tests
against disposable PostgreSQL and Redis:

- `tests/test_holds.py::test_many_patients_one_reservation_and_no_deadline_extension`
- `tests/test_holds.py::test_expired_hold_reallocated_atomically`
- `tests/test_recovery.py::test_late_success_competing_with_new_hold_never_double_books`
- `tests/test_payments.py::test_concurrent_distinct_events_emit_one_confirmation`

These tests exercise persisted exclusivity, late-payment/new-hold races and a
single confirmation outbox event. Their authoritative billing responses are
fixtures. They do not establish competing real Stripe payments or AWS
integration. The live checker covers reservation contention and natural expiry;
the separate I01 evidence covers a real local Stripe test-payment journey.

Three cleanup regressions cover a failed resource request, failed withdrawal and
token revocation, and cancellation racing expiry. Scheduling CI runs these and
lints the checker; the ten-minute local journey is an explicit operator check.
