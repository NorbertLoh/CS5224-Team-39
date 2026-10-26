# Deeper backend cleanup (RF21)

Issue #302; assigned to NorbertLoh and marked In progress. Based on merged cleanup
stack #297-#301. Status: audit complete; implementation/checks in progress.

## Inspected scope and decisions

Inspected the runtime module inventory across all ten Python services (including
the template), shared Python foundations and the signalling service. Compared
pagination implementations, startup/resource lifetime, HTTP boundaries, worker
entry points, fixture consumers and top-level symbol references across source/tests.
The largest runtime modules remain below 300 lines; size alone does not justify splitting.

| Area | Finding and action |
| --- | --- |
| Identity, tenant, scheduling, billing, fulfilment, clinical records, document | Repeated HS256 cursor signing/expiry/required-claim mechanics. Extract only these technical mechanics into `telelink_common.pagination`; keep resource claims, scopes, parsing, errors and queries local. Include the identity doctor-directory cursor. |
| Fulfilment | `DispensingSource` protocol has no consumer in source/tests; remove it and its otherwise-unused Protocol import. Keep the actual HTTP/fixture adapters and their safeguards. |
| Notification | `EmailSender` protocol has no consumer in source/tests; remove it and the unused Protocol import. Keep SES behavior and provider error handling unchanged. |
| Consultation, service HTTP clients and startup | Different timeouts, authentication, endpoint/status rules and close behavior are intentional. Keep these service-local rather than wrapping them in a generic client/factory. |
| Signalling | Admission/parser/shutdown code and active tests remain separate from Python cursor mechanics; no proven unused runtime code identified. Keep unique media/TURN spike checks. |
| Models, migrations, workers, tests and fixtures | Active schema/transaction ownership and verification consumers. No keyword-based deletion or database change. |

No API/event contract, environment variable, cursor issuer/audience/lifetime,
scope binding, response shape or dependency version changes are intended.
Already-issued cursors must remain readable. The tenant admin cursor's nullable
status remains present-but-not-required by JWT's non-null claim rule.
Authorization, tenant filtering and SQL pagination remain in each owning service.

## Verification plan and evidence

- Preserve existing service cursor functions and return types for their callers.
- Check shared JWT behavior: expiry, wrong key/algorithm/issuer/audience, required
  fields and missing configuration; do not move business authorization into shared code.
- Compare old and new encoders/decoders in both directions using equivalent rows,
  roles, scopes and filters, including tampering and nullable admin status.
- Run shared tests and available service tests locally without a persistent data reset.
- Require existing per-service PostgreSQL CI and Ruff checks for the shared change.
- No frontend, provider transaction, Compose startup or deployment needed for this refactor.

Results: pending. Required manual UI follow-ups from RF17/RF20 stay in their
existing issues and are not established by backend checks.
