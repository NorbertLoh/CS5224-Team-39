# Local development

Compose runs the FastAPI template alongside PostgreSQL, Redis and optional
Floci. Run the frontend on the host; Vite forwards `/api/v1/template` to the
API container. Bootstrap supplies S3, synthetic secrets, messaging and Cognito
below; [F14 shared workflow fixtures](../dev/fixtures/README.md) supply a static
two-clinic dataset for mock UI/service development. Validate it from the root with
`python dev/fixtures/validate.py`; it is independent of Floci bootstrap and does
not load live service databases or grant login/membership access.

## Start

Use Docker Desktop with Linux containers (or Linux Docker Engine) and Compose
v2 supporting `up --wait`. From the repository root, in PowerShell:

```powershell
Copy-Item .env.example .env
docker compose --profile offline config --quiet
docker compose --profile offline up --build -d --wait
docker compose --profile offline ps
```

Copy the example only on first setup; preserve existing overrides. `.env` is
ignored by Git and contains synthetic values. Change `*_PORT` values if a port
is occupied. First startup downloads images; once cached, use
`docker compose --profile offline up --pull never -d --wait` without downloading.

The template API and PostgreSQL/Redis run in both profiles. `offline` also starts
Floci; `connected` does not configure real Cognito or providers.
Plain `docker compose up` starts the API and PostgreSQL/Redis. Stop the
offline stack before switching profiles: profiles do not stop running containers.

Initial images are PostgreSQL 17, Redis 7.4 Alpine and released Floci 2.2.0.
Override references in `.env` if needed. F16 validates required Floci operations
before treating this selection as the tested emulator baseline.

In a second terminal, start the frontend:

```powershell
cd apps/web
npm ci
npm run dev
```

Open `http://localhost:5173`. Check API forwarding with:

```powershell
Invoke-RestMethod http://localhost:5173/api/v1/template/health/ready
```

Expected result: `status: ready`, `service: template`. Swagger UI is at
`http://localhost:5173/api/v1/template/docs`. Vite strips `/api/v1/template`
before forwarding; the API uses this root path for generated docs URLs.
Only the template prefix is wired; other service routes are added by their tasks.
Vite preview also uses this proxy for local build checks. Production routing
remains W04; the proxy is not included in the static frontend build.

If port 8000 is occupied, change `TEMPLATE_HOST_PORT` in the root `.env` and set
`TEMPLATE_API_TARGET=http://127.0.0.1:<port>` in `apps/web/.env`, then restart
Compose and Vite. Keep `VITE_API_BASE_URL=/api/v1` for same-origin requests.
The template runs the production image locally with docs enabled, without hot
reload. For API reload, use the [standalone development override](../services/template/docs/containers.md).

## Bootstrap local resources

From the repository root, after starting the offline stack:

```powershell
docker compose --profile offline run --rm bootstrap
```

The runner waits for healthy Floci and creates these resources:

| Resource | Name | Initial contents |
| --- | --- | --- |
| S3 bucket | `telelink-local-documents` | Empty; public access block enabled |
| Secrets Manager secret | `telelink/local/stripe` | JSON: `api_key`, `webhook_secret` |
| Secrets Manager secret | `telelink/local/lalamove` | JSON: `api_key`, `api_secret` |
| EventBridge bus | `telelink-local` | Four enabled consumer rules |
| SQS consumer queues | `telelink-local-{scheduling,fulfilment,document,notification}` | Empty; one queue per consumer |
| SQS processing DLQs | Each consumer queue name plus `-dlq` | Empty; redrive after three receives |
| SQS delivery DLQ | `telelink-local-event-delivery-dlq` | Empty; captures EventBridge delivery failures |
| Cognito pool / public SPA client | `telelink-local` / `telelink-web` | Authorization code flow; no client secret |
| Cognito groups / users | `patient`, `doctor`, `clinic_admin`, `platform_admin` | Four confirmed local demo users |

All secret values are clearly synthetic and cannot call the real providers.
Bootstrap creates missing resources, preserves existing objects and secret
values and queue messages. It reapplies the bucket public access block and
managed queue/rule/target settings without publishing or consuming events.
Errors stop the script
with a nonzero exit code. Run it again after resetting the Floci volume.

The separate `bootstrap` profile keeps this one-shot job out of ordinary `up`
and `up --wait`. `run bootstrap` selects it explicitly; keep `--profile offline`
to include its Floci dependency. The pinned AWS CLI container needs no host AWS
installation or credentials. It always calls `http://floci:4566` with dummy
credentials, regardless of host AWS settings or `FLOCI_PORT`.

First use downloads `amazon/aws-cli:2.37.11`. With that image cached, use
`docker compose --profile offline run --rm --pull never bootstrap` offline.
For inspection with the same isolated CLI, override its entrypoint:

```powershell
docker compose --profile offline run --rm --entrypoint aws bootstrap --endpoint-url http://floci:4566 s3api list-buckets
docker compose --profile offline run --rm --entrypoint aws bootstrap --endpoint-url http://floci:4566 secretsmanager list-secrets
```

Emulator settings do not establish AWS authorization or privacy guarantees.
Real private S3/IAM configuration belongs to W08; restart/API coverage remains
F16. Business services must configure these resource names and read secrets
server-side; never copy provider secrets into frontend `VITE_*` variables.

### Event routes and queue access

The [C05 event contract](../contracts/events.md) defines exact source/type pairs,
payloads, queue names and retry settings. `events.sh` applies those routes using
the committed `dev/floci/patterns/` files. Consumer queues retain messages for
four days, use a 30-second visibility timeout and redrive after three receives.
DLQs retain messages for 14 days. EventBridge targets retry three times within
one hour and send delivery failures to the shared delivery DLQ. These settings
are local defaults; worker acknowledgement, idempotency and operator replay
remain M03/M04, and full emulator compatibility remains F16.

Inspect the bus and queues without publishing workflow events:

```powershell
docker compose --profile offline run --rm --entrypoint aws bootstrap --endpoint-url http://floci:4566 events list-rules --event-bus-name telelink-local
docker compose --profile offline run --rm --entrypoint aws bootstrap --endpoint-url http://floci:4566 sqs list-queues --queue-name-prefix telelink-local-
```

Floci returns host-facing queue URLs using `FLOCI_BASE_URL`. Container tools
must replace only that URL's origin with `http://floci:4566`, preserving its
account/queue path; host tools keep the original URL (adjusted by `FLOCI_PORT`).
The bootstrap runner does this when configuring queues. Use matching region and
dummy credentials. Production SDKs use AWS queue URLs without this local rewrite.
The synthetic contract fixtures are for isolated routing checks with workers
stopped; bootstrap never sends them automatically.

### Cognito demo identities

`cognito.sh` creates the pool/client and prints `COGNITO_USER_POOL_ID`,
`COGNITO_CLIENT_ID` and `COGNITO_ISSUER`. IDs are generated by Cognito and remain
stable across bootstrap reruns; resetting the Floci volume generates new IDs.
The public client allows authorization code flow with `openid email profile`
scopes and refresh, without a client secret. A01 implements the frontend PKCE
login/return flow; this task seeds its prerequisites only.

| Username | Seed group |
| --- | --- |
| `patient@example.test` | `patient` |
| `doctor@example.test` | `doctor` |
| `clinic@example.test` | `clinic_admin` |
| `platform@example.test` | `platform_admin` |

Initial password for all four synthetic users: `LocalDemo123!`. Creation
suppresses invitation messages and marks their `.test` email addresses verified.
Only users in `FORCE_CHANGE_PASSWORD` receive the permanent seed password, so
reruns resume interrupted creation and preserve confirmed users' changed
passwords and disabled state. Reruns ensure seed group membership and update
the managed client settings. Duplicate named pools/clients or an existing
confidential client cause an error rather than silently selecting an identity.

Root `.env` configures the exact allowed URLs:

```dotenv
COGNITO_CALLBACK_URL=http://localhost:5173/auth/callback
COGNITO_LOGOUT_URL=http://localhost:5173/
```

These are reserved A01/A02 routes; the frontend does not handle authentication
yet. For another frontend port or `127.0.0.1`, change both URLs and rerun
bootstrap. Cognito matches redirect URLs exactly.

For the printed issuer `http://localhost:<FLOCI_PORT>/<pool-id>`, discovery and
JWKS are `<issuer>/.well-known/openid-configuration` and
`<issuer>/.well-known/jwks.json`. Use the endpoints advertised by discovery for
authorization/token requests. The pinned release serves managed login at
`/cognito-idp/login`; it needs no AWS-style domain. Inside Compose, fetch JWKS
from `http://floci:4566/<pool-id>/.well-known/jwks.json` but validate the original
host-facing issuer in tokens. Do not rewrite token claims or use ID tokens as
API access tokens. A03 implements verification; A02/F16 verify lifecycle and
emulator behavior, and W05 verifies real AWS Cognito.

Groups are synthetic role fixtures, not clinic memberships or an authorization
bypass. Identity/access tasks own server-controlled roles and tenant checks.
No real signup, email delivery, MFA or business-service access is configured.

## Endpoints

| Dependency | Host (default ports) | Inside Compose |
| --- | --- | --- |
| Template API | `http://localhost:8000` | `http://template:8000` |
| PostgreSQL | `localhost:55432`, database `telelink` | `postgres:5432` |
| Redis | `redis://localhost:6379/0` | `redis://redis:6379/0` |
| Floci | `http://localhost:4566` | `http://floci:4566` |

Host port overrides do not change container ports. Floci-generated URLs use the
host-facing base. Bootstrap/API tasks must handle host/container reachability for
queue URLs, Cognito issuers and signed downloads.

The PostgreSQL login is a local provisioning administrator. Services must create
their own roles/schemas and run migrations, rather than use that login for
application access. Follow the template's [database guide](../services/template/docs/database.md)
for its role/schema and migrations. This startup leaves the template's optional
database mode disabled; it creates no application tables or roles. Its readiness
check confirms API startup only, not a database integration.

Compose reads `.env` but does not export it to your host shell. For local SDK/CLI
calls, use dummy credentials and an explicit endpoint, for example:

```powershell
$env:AWS_ACCESS_KEY_ID = 'test'
$env:AWS_SECRET_ACCESS_KEY = 'test'
$env:AWS_DEFAULT_REGION = 'ap-southeast-1'
aws --endpoint-url http://localhost:4566 s3api list-buckets
```

Adjust the endpoint for `FLOCI_PORT`. Use a separate shell for real development
AWS calls so local overrides are not mixed with cloud access.

## Check and stop

```powershell
docker compose exec postgres pg_isready -U postgres -d telelink
docker compose exec redis redis-cli ping
Invoke-RestMethod http://localhost:8000/health/live
Invoke-RestMethod http://localhost:4566/_floci/health
docker compose --profile offline logs --tail 50
docker compose --profile offline down
```

Adjust the PostgreSQL user/database arguments if changed in `.env`. Health
checks show basic availability, not full AWS compatibility. Ports bind to
localhost. There is no Docker socket mount; Floci's UI sidecar is disabled.

Named volumes retain PostgreSQL, Redis AOF and Floci persistent storage during
normal `down`/`up`. F16 verifies Floci persistence service by service. Changing
PostgreSQL credentials in `.env` does not change an initialized database; update
them through PostgreSQL or use a fresh disposable Compose project.

For an intentional reset, `docker compose --profile offline down --volumes`
erases this project's `postgres_data`, `redis_data` and `floci_data` volumes.
Confirm the project first: default `telelink`, overridden by
`COMPOSE_PROJECT_NAME` or `-p`. Never reset shared data accidentally.

References: [PostgreSQL image](https://hub.docker.com/_/postgres),
[Redis image](https://hub.docker.com/_/redis), Floci 2.2.0
[storage configuration](https://github.com/floci-io/floci/blob/2.2.0/src/main/resources/application.yml)
and [health check](https://github.com/floci-io/floci/blob/2.2.0/docker/healthcheck.sh).
