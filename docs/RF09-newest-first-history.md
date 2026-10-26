# RF09 history ordering

Payments, medicine/delivery orders, prescriptions and documents now load newest
creation time first, with descending resource ID as a stable tie-breaker. This is
server-side ordering across every page, so recent records appear immediately.
The payment history caption reflects the ordering. Patient and clinic-admin order
workspaces request `sort=newest`; the orders API also defaults to newest first.
Explicit `sort=oldest` remains supported for clients that need it.

Direction is bound to the pagination cursor. Ascending payment, prescription and
document cursors issued before this change are rejected; refresh the history to
start again. Existing explicit newest-order cursors remain valid. Access checks,
filters, audit behavior and immutable financial snapshots remain unchanged.

Patient document grouping remains newest visit first and prescriptions retain
their issued-date display ordering. Upcoming appointments and slots remain in
chronological order; clinic/catalogue lists retain name ordering. Background
worker queues retain their processing order.

No migration, new configuration or worker restart is needed. Restart billing,
fulfilment, clinical-records and document APIs after updating the code. Vite loads
the frontend changes automatically in the host development stack.

Verification: billing payment query tests 28 passed; document API tests 26 passed;
clinical-records API tests 28 passed; fulfilment API tests 42 passed. These ran
against isolated service schemas in a disposable PostgreSQL container. Checks
cover descending page boundaries, timestamp ties, newly inserted payments,
filters, authorization, audits and cross-direction cursor rejection. Frontend
lint/typecheck/build and backend Ruff are required before review.

Frontend lint/typecheck/production build and backend Ruff passed. After restarting the four APIs, live Tailscale checks verified descending order across two pages (six rows each) for patient payment, order, prescription and document histories, and clinic-admin payment/order histories. All eight local APIs remain ready. No business data was reset and no provider operations were performed.
