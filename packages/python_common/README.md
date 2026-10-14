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
locations only, never payload values. Persisting the outbox (M02) and inbox
deduplication/acknowledgement (M03) remain separate tasks.

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

M01 also verified one live Floci PutEvents -> `telelink-local-notification`
round trip through `create_client`, `to_put_events_entry` and `parse_sqs_body`.
Identity's full PostgreSQL/token suite uses the same package. A06 also verifies
real HTTP between template and identity, live Floci JWT/JWKS, PostgreSQL membership
and immediate revocation. Live tenant/scheduling business integration remains
future work.
