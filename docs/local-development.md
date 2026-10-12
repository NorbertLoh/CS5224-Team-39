# Local development

F09 supplies PostgreSQL, Redis and Floci dependencies. Run the frontend and
[service template](../services/template/README.md) separately. F10 adds the
API/proxy; F11-F14 add resource bootstrap and synthetic fixtures.

## Start

Use Docker Desktop with Linux containers (or Linux Docker Engine) and Compose
v2 supporting `up --wait`. From the repository root, in PowerShell:

```powershell
Copy-Item .env.example .env
docker compose --profile offline config --quiet
docker compose --profile offline up -d --wait
docker compose --profile offline ps
```

Copy the example only on first setup; preserve existing overrides. `.env` is
ignored by Git and contains synthetic values. Change `*_PORT` values if a port
is occupied. First startup downloads images; once cached, use
`docker compose --profile offline up --pull never -d --wait` without downloading.

PostgreSQL/Redis run in both profiles. `offline` also starts Floci; `connected`
currently starts only PostgreSQL/Redis and does not configure real Cognito or
providers. Plain `docker compose up` starts only PostgreSQL/Redis. Stop the
offline stack before switching profiles: profiles do not stop running containers.

Initial images are PostgreSQL 17, Redis 7.4 Alpine and released Floci 2.2.0.
Override references in `.env` if needed. F16 validates required Floci operations
before treating this selection as the tested emulator baseline.

## Endpoints

| Dependency | Host (default ports) | Inside Compose |
| --- | --- | --- |
| PostgreSQL | `localhost:55432`, database `telelink` | `postgres:5432` |
| Redis | `redis://localhost:6379/0` | `redis://redis:6379/0` |
| Floci | `http://localhost:4566` | `http://floci:4566` |

Host port overrides do not change container ports. Floci-generated URLs use the
host-facing base. Bootstrap/API tasks must handle host/container reachability for
queue URLs, Cognito issuers and signed downloads.

The PostgreSQL login is a local provisioning administrator. Services must create
their own roles/schemas and run migrations, rather than use that login for
application access. Follow the template's [database guide](../services/template/docs/database.md)
for its role/schema and migrations. F09 creates no application tables or roles.

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
