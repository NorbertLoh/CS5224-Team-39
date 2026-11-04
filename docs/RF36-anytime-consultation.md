# Anytime consultation access (RF36)

Assigned doctors can start a paid confirmed consultation before or after its
scheduled slot. The booked patient and assigned doctor can open or rejoin its
video while the appointment is confirmed or in progress, until the doctor uses
End consultation. Opening or leaving video does not start or end clinical care.
End consultation retains prescription issuance and MC finalization.

Current participant, tenant, membership, payment and status checks remain on
admission, connection and lease renewal. Completed, cancelled, no-show, unpaid,
refunded and revoked access remain denied. No-show and booking/payment hold rules
retain their existing time gates. Scheduled times remain immutable context and
still determine appointment sorting and Upcoming/Past placement.

Join credentials remain single-use and short-lived. Active leases renew without
the scheduled-end clamp and retain the configured maximum call deadline and TURN
credential expiry. A fresh authorized rejoin obtains new credentials. This change
does not turn credentials into permanent access.

## Deployment

Back up the consultation schema, then apply consultation migration `0006` with
`python -m alembic upgrade head`. Deploy matching consultation, scheduling and web
builds. Consultation readiness requires revision `0006`. No new environment
variables or scheduling migration are required. Existing test-window settings are
retained for compatibility and historical data; they no longer limit access.

Migration `0006` retains finite actual-start validation and ordered end timestamps
while permitting starts outside the booked slot. It preserves existing timestamps
and the immutable appointment snapshot. Downgrade refuses when an actual start
would violate the old interval constraint; it never rewrites clinical history.

## Verification

All 157 consultation tests and 272 scheduling tests (2 skips) passed, including
early/late start and admission, renewal across scheduled end, participant/payment
denials, completed-session closure, retries and guarded migration downgrade.
Backend Ruff and frontend lint/typecheck/build passed. The local consultation
schema was backed up before applying `0006`; consultation, scheduling and web are
healthy and the existing Tailscale endpoint serves the updated controls. No real
consultation was started or completed during verification. AWS remains unverified.
