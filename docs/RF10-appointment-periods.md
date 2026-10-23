# RF10 appointment periods

Patient, doctor and clinic-admin appointment workspaces share **Upcoming** and
**Past** tabs, including clinic-specific appointment pages. Upcoming opens by
default; cards show each booking once with its full Singapore date and time range.
Staff see patient/clinic/doctor names appropriate to their role and retain their
existing detail actions. The overall clinic-admin page keeps its clinic selector;
the selected-clinic page has no selector. Switching period or clinic clears details.

`GET /appointments?period=upcoming` returns active (`held`, `pending_payment`,
`confirmed`, `in_progress`) appointments whose end time is later than server time,
ordered by start time then ID ascending. Effective hold expiry is applied before
classification, so an expired unpaid hold is not shown as upcoming.
`period=past` returns the complement, including cancelled/completed/expired/no-show
bookings regardless of their scheduled date, ordered by start time then ID descending.
Expiry and classification use the same statement timestamp within each SQL query.

The server filters before pagination. Each tab has its own cursor/query cache,
loading/error/empty state and Load more action. The displayed count refers to
loaded records, not a claimed total. Period and direction are bound to cursors;
cross-tab and filtered/unfiltered cursor reuse returns 422. Omitting `period`
retains the existing ascending list contract for other clients.

The selected clinic, patient ownership, doctor assignment and current membership
checks remain enforced by scheduling. Booking, availability, cancellation, payment,
refund and consultation admission rules are unchanged. No migration or new
configuration is needed; restart only the scheduling API in the host stack.
The frontend uses the existing live detail refresh and 15-second list polling.

Verification includes active/ongoing/ended and terminal classification, effective
expiry, first-page upcoming visibility, both pagination directions, timestamp ties,
cross-period cursor rejection and current patient/doctor/clinic membership scopes.
Use only disposable PostgreSQL for reset-enabled scheduling tests. Frontend lint,
typecheck/build and live remote browser checks are required before review.

Local verification: 55 appointment/period API tests passed, with two Redis-dependent checks skipped locally; Ruff and frontend lint/typecheck/production build passed. Real Tailscale API checks verified period classification, ordering, pagination and scope for patient, doctor and clinic-admin accounts. Browser checks verified the clinic-admin empty state, descending Past cards, detail selection and clearing on tab change, changing clinics, the clinic-specific route without a selector, one upcoming booking with its full SGT date/time and keyboard tab switching. Scheduling readiness remains HTTP 200 after its API restart. No business data reset or provider operations were needed.
