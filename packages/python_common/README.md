# Shared Python foundations (A06)

`telelink_common` is an internal installable package used by identity and the
service template. Domain models, migrations, transactions, readiness checks,
business routes and scheduling service credentials stay service-local.

| Module | Responsibility |
| --- | --- |
| `settings` | Validated `SERVICE_*` settings, Cognito/TLS guards and reusable name/port field types |
| `auth` | A03 Cognito RS256 access-token verification and bearer dependency |
| `access` | Current identity HTTP lookup, tenant/global role helpers and dependencies |
| `database` | PostgreSQL engine construction, timeouts, UTC and safe parameter handling |
| `errors` | C01 error envelopes, response models and safe handlers |
| `logging`, `middleware` | JSON logs, request IDs and request timing |
| `events` | M01 C05 event envelope, type/route registry, PutEvents entries and SQS body parsing |
| `aws` | M01 boto3 client construction from region/endpoint settings (`aws` extra) |
| `outbox` | M02 outbox table, transactional event staging and retrying PutEvents publisher |
| `inbox` | M03 inbox table and SQS consumer helper with deduplication and acknowledgement |

## Install

From a service directory, after creating its virtualenv:

```powershell
.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
.venv\Scripts\python.exe -m pip install --no-deps --no-build-isolation -e ../../packages/python_common
.venv\Scripts\python.exe -m pip install --no-deps --no-build-isolation -e .
```

Service metadata requires `telelink-python-common==0.1.0`, provided from the
repository rather than a public package index. External versions remain pinned
by service lockfiles. Containers install a wheel; local installs are editable.
Use shared imports directly and extend `ServiceSettings` locally instead of
copying validators. The shared `ServiceName`/`ServicePort` types retain validation
when a service changes its defaults.

## Reusable checks

`require_tenant_role('clinic_admin')` requires an active membership in the path's
`tenant_id`. `require_global_role('patient')` checks persisted global roles.
`allow_platform_admin=True` is an explicit exception for C02 operational policies,
disabled by default; it must not implicitly grant doctor/clinical permissions.
Pure `has_tenant_role`/`has_global_role` helpers work with service-local models.
See the [template endpoint](../../services/template/app/access.py) and
[setup guide](../../services/template/docs/access.md).

Initialize `app.state.token_verifier` and `app.state.identity_client` in a service
factory, use common request-ID middleware, and close the client on shutdown.
Set `SERVICE_IDENTITY_URL` to the trusted identity base URL: direct local example
`http://localhost:8001`, or an ingress base ending `/api/v1/identity`. The client
appends `/me`. Non-local URLs require HTTPS without credentials/query/fragment;
redirects are not followed. `SERVICE_IDENTITY_TIMEOUT_SECONDS` defaults to 3.

Each request verifies the token locally, forwards the same bearer token to
identity's authenticated `/me`, validates membership ownership/shape, and checks
the returned Cognito sub matches the verified principal. Identity independently
authenticates the token and loads current permissions. No cross-request permission
cache exists. Revocation is observed on the next lookup. Spoofed headers, browser
roles and Cognito groups do not establish access.

Missing configuration/network failures fail closed with 503; malformed upstream
data returns 502; unauthorized clinic access is concealed with 404. Role checks
do not assert resource existence or legal domain state. Owning services must check
their resource tenant/participants, transaction state and auditing at the operation
boundary. No video admission permission is implied. No utility reads another
service's database.

## Workflow events (M01)

`telelink_common.events` implements the [C05 contract](../../contracts/events.md).
Producers create an event for a committed fact and keep its `event_id` for retries:

```python
event = new_event(
    "appointment_confirmed.v1",
    tenant_id=appointment.tenant_id,
    correlation_id=correlation_id,
    occurred_at=appointment.confirmed_at,
    data={"appointment_id": appointment.id},
)
entry = to_put_events_entry(event, settings.event_bus_name)
```

`Source` comes from the registry, `Time` equals `occurred_at` and `Detail` is
serialized once. Consumers call `parse_sqs_body(message["Body"], consumer="notification")`,
which parses the EventBridge wrapper once and returns a typed `WorkflowEvent`.
It raises `EventValidationError` for malformed JSON, unknown types or versions,
source/type mismatches, events not routed to that consumer, invalid IDs, money or
timestamps. Do not acknowledge those messages; bounded receives move them to the
consumer DLQ. Unknown optional fields are ignored. Error messages list field
locations only, never payload values. Producers publish through the outbox and consumers receive through the inbox
helper below.

## Transactional outbox (M02)

A producer saves its domain change and the event in one transaction, so an event
is published only for committed facts and is never lost after commit. Add the
table to the service's own metadata (its schema) and migration:

```python
# app/models.py
from telelink_common.outbox import outbox_table

event_outbox = outbox_table(Base.metadata)  # SERVICE_SCHEMA.event_outbox
```

Generate the service migration with `alembic revision --autogenerate`; it creates
`event_outbox` plus the partial index `ix_event_outbox_pending`. Then stage the
event in the same transaction as the change:

```python
with session.begin():
    appointment.status = "confirmed"
    add_event(session, event_outbox, new_event("appointment_confirmed.v1", ...))
```

A worker process (like scheduling's `app.expire_holds`) publishes due rows:

```python
client = create_client("events", settings)
while True:
    result = publish_pending(sessions, event_outbox, client, settings.event_bus_name)
    if not (result.published or result.failed):
        time.sleep(1)
```

`publish_pending` sends up to 10 due rows in one PutEvents call. Accepted entries
get `published_at`; failed entries keep their stored envelope and `event_id`, get
`attempts + 1`, the EventBridge error code (or exception type) in `last_error`,
and retry after 5s, 10s, 20s ... capped at 5 minutes. Successful siblings are
not resent. Rows stay locked (`FOR UPDATE SKIP LOCKED`) until the outcome is
saved, so several workers never send the same row concurrently; the SDK timeouts
bound that lock. A crash between PutEvents and saving the outcome can resend an
event with the same `event_id`, which consumers deduplicate with the inbox.

Check publication with SQL, for example
`SELECT detail_type, attempts, last_error FROM <schema>.event_outbox WHERE published_at IS NULL`.
Stored rows contain IDs only, never clinical notes. Prune old published rows in
a later reviewed migration or job if the table grows.

## Consumer inbox (M03)

Delivery is at least once, so a consumer records each handled event in its own
inbox in the same transaction as its state change. Add the table to the
service's metadata and migration, like the outbox:

```python
# app/models.py
from telelink_common.inbox import inbox_table

event_inbox = inbox_table(Base.metadata)  # SERVICE_SCHEMA.event_inbox, key (consumer, event_id)
```

Write a handler that makes the state change with the given session (do not
commit; the helper does), then run a worker loop:

```python
def confirm_payment(session, event):
    appointment = session.get(Appointment, event.data.appointment_id)
    appointment.status = "confirmed"

sqs = create_client("sqs", settings)
queue_url = sqs.get_queue_url(QueueName="telelink-local-scheduling")["QueueUrl"]
while True:
    consume_batch(sessions, event_inbox, sqs, queue_url, "scheduling", confirm_payment)
```

`consume_batch` long-polls up to 10 messages (20s wait) and, for each one:

- parses the body once with `parse_sqs_body` for that consumer;
- skips the handler if `(consumer, event_id)` is already in the inbox (a duplicate);
- otherwise inserts the inbox row and runs the handler in one transaction;
- deletes the message only after that commit, or for a duplicate.

Handler errors roll back both the state change and the inbox row, and the
message is left on the queue. Malformed, unknown or misrouted events are never
deleted. Either way SQS redelivers after the 30s visibility timeout and moves the
message to the consumer DLQ after 3 receives (M04 covers replay). Logs record
only `inbox_message_failed` with the exception type. If a delete fails after
commit, the redelivered message is skipped as a duplicate. Two workers handling
the same event at once conflict on the inbox key; the loser rolls back and later
sees a duplicate. Keep handlers well under the visibility timeout, and give
external side effects (email, payment, delivery calls) their own idempotency key,
since the inbox protects database changes only.

## AWS SDK configuration (M01)

| Setting | Default | Purpose |
| --- | --- | --- |
| `SERVICE_AWS_REGION` | `ap-southeast-1` | SDK region |
| `SERVICE_AWS_ENDPOINT_URL` | unset | Emulator override: `http://floci:4566` in Compose, `http://localhost:4566` on the host |
| `SERVICE_EVENT_BUS_NAME` | unset | EventBridge bus; `telelink-local` in Floci |

The endpoint override is accepted only in `local`/`test` environments and only
for `localhost`, `127.0.0.1` or `floci`; AWS deployments omit it. Credentials are
never configured here: local runs use the dummy `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY`
values and AWS uses the task role. `create_client("events", settings)` applies
3s connect/10s read timeouts and standard retries. boto3 is the optional `aws`
extra; services that publish or consume events add a pinned `boto3` to their own
lockfile.

## Verification

From `services/template`, run shared and service tests:

```powershell
.venv\Scripts\python.exe -m pytest ../../packages/python_common/tests -q
.venv\Scripts\python.exe -m pytest tests -q
.venv\Scripts\python.exe -m ruff check ../../packages/python_common
```

Outbox tests use SQLite and a fake EventBridge client; with `TEST_DATABASE_URL`
set to a disposable service database (schema named after its role), a PostgreSQL
test also checks that concurrent publishers skip locked rows. Inbox tests run on
SQLite and, with `TEST_DATABASE_URL`, on PostgreSQL too.

M01 also verified one live Floci PutEvents -> `telelink-local-notification`
round trip through `create_client`, `to_put_events_entry` and `parse_sqs_body`.
Identity's full PostgreSQL/token suite uses the same package. A06 also verifies
real HTTP between template and identity, live Floci JWT/JWKS, PostgreSQL membership
and immediate revocation. Live tenant/scheduling business integration remains
future work.
