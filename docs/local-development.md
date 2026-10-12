# Local development

Compose runs the FastAPI template alongside PostgreSQL, Redis and optional
Floci. Run the frontend on the host; Vite forwards `/api/v1/template` to the
API container. F11 supplies the S3/secrets bootstrap below; F12-F14 add messaging,
Cognito and synthetic workflow fixtures.

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

## Bootstrap S3 and synthetic secrets

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

All secret values are clearly synthetic and cannot call the real providers.
Bootstrap creates missing resources, preserves existing objects and secret
values, and reapplies the bucket's public access block. Errors stop the script
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
