# Template containers

Run from `services/template` with Docker Desktop using Linux containers. These files run only the generic API; F09/F10 supply the shared PostgreSQL/Redis/Floci stack later.

## Production-style local run

```powershell
docker compose -f compose.template.yaml up --build -d
docker compose -f compose.template.yaml logs template
```

Open `http://localhost:8000/health/live` and `/health/ready`. Docs default off in production. The image runs as UID 10001, logs JSON to stdout, installs only declared runtime dependencies under the checked-in lockfile constraints, and excludes local environment files/caches from its build context. Dev tools are installed only in the development target.

The image's liveness health check uses port 8000. When deploying to ECS, keep that container port or update the check deliberately; configure the load balancer to use `/health/ready`. When database mode is enabled, pass `SERVICE_DATABASE_URL` explicitly and run migrations separately before routing traffic. No credentials are baked into this image.

Stop this standalone service:

```powershell
docker compose -f compose.template.yaml down
```

## Source reload

```powershell
docker compose -f compose.template.yaml -f compose.template.dev.yaml up --build
```

The override mounts source at `/app`, enables docs and watches `/app/app` with Uvicorn's reload process. Edit an application file and the server reloads. Limiting the watch directory avoids traversing a host `.venv`, which can make Windows bind-mount reload very slow. Dependency changes require rebuilding; changes outside `app/` require a restart. Development uses Uvicorn's default logs with raw access logs disabled; production uses the JSON entry point. Do not deploy the development target or source mount on AWS.

If port 8000 is occupied, set `$env:TEMPLATE_HOST_PORT = '18005'` before the Compose command. The internal port remains 8000. On Linux/macOS, set the equivalent shell environment variable.

## Direct builds and checks

```powershell
docker build --target production -t telelink-template:local .
docker build --target development -t telelink-template:dev .
docker run --rm telelink-template:dev python -m pytest
```

The Python base tag is a maintained version tag rather than an immutable digest. Pin the approved digest in infrastructure when reproducible deployment images are required; deployed service images should use immutable commit tags.
