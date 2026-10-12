# FastAPI service template

F03 provides environment settings, JSON logs, request correlation, lifecycle health probes and OpenAPI. Copy this directory into a business-service directory when its task is claimed; do not import another service's `app` package. Database access/migrations belong to F04 and Dockerfiles to F05.

## Install and run (PowerShell)

Run from this directory. Python 3.10 or newer is required; validation currently uses Python 3.10.8.

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
.venv\Scripts\python.exe -m pip install --no-deps --no-build-isolation -e .
Copy-Item .env.example .env
.venv\Scripts\python.exe -m app
```

The lockfile includes development tools and build dependencies for a repeatable local install. To deliberately update dependency resolution, install `-e ".[dev]"` and regenerate the lockfile using `pip freeze --exclude-editable`; review and verify the update before committing it. On Linux/macOS, use `.venv/bin/python` in place of the Windows interpreter path.

Default URLs:

- `http://127.0.0.1:8000/health/live`: HTTP 200 while the process can serve requests, independent of dependencies.
- `http://127.0.0.1:8000/health/ready`: HTTP 200 after startup; HTTP 503 before startup/after teardown.
- `http://127.0.0.1:8000/docs`, `/redoc`, `/openapi.json`: interactive docs and schema.

The template has no external dependencies, so readiness only reflects lifecycle startup. Services adding a database or other essential resources must initialise them before becoming ready and extend the readiness check appropriately. It is not currently a database/connectivity check.

## Configuration

Environment variables override `.env`. The `.env` is loaded relative to the working directory; run each service from its own directory. Never commit real environment files.

| Variable | Default | Meaning |
| --- | --- | --- |
| `SERVICE_NAME` | `template` | Lowercase service identifier, used in title/probes/logs |
| `SERVICE_ENVIRONMENT` | `local` | `local`, `test`, `development`, `demo`, `production` |
| `SERVICE_HOST` | `127.0.0.1` | Listen interface; container tasks can use `0.0.0.0` |
| `SERVICE_PORT` | `8000` | Port between 1 and 65535 |
| `SERVICE_LOG_LEVEL` | `INFO` | Standard uppercase logging level |
| `SERVICE_DOCS_ENABLED` | automatic | Defaults off for production, on otherwise; explicit true/false overrides |
| `SERVICE_ROOT_PATH` | empty | Proxy-stripped path prefix for generated URLs, not a router prefix |

Invalid settings fail startup. Do not place provider credentials in frontend configuration. Authentication is not implemented by this template.

## Logging and correlation

`python -m app` configures JSON stdout logs and disables Uvicorn's raw access logs. HTTP logs contain the method, matched route template, status, duration, service and request ID. A supplied `X-Request-ID` is accepted only when it contains 1-64 letters, digits, dots, underscores or hyphens; otherwise a new UUID is generated. This value supports correlation and is not an identity/authentication assertion.

Automatic logs omit raw URLs/query strings, headers, request/response bodies and exception text. The formatter includes the exception type only. Application authors must still avoid putting secrets/clinical data in their own log messages. Health and normal responses carry `X-Request-ID`.

For development reload only:

```powershell
.venv\Scripts\python.exe -m uvicorn app.main:create_app --factory --reload --no-access-log
```

The direct Uvicorn command uses its own logging configuration rather than the JSON entry point, and does not read `SERVICE_HOST`/`SERVICE_PORT` for server binding. Use `python -m app` for the documented runtime behaviour.

## Verify

```powershell
.venv\Scripts\python.exe -m pytest
.venv\Scripts\python.exe -m ruff check app tests
.venv\Scripts\python.exe -m ruff format --check app tests
```

The focused tests cover environment validation, readiness lifecycle, production docs, request correlation and omission of sensitive request/exception text. No PostgreSQL, Floci, AWS or credentials are needed.

## Copying into a service

Copy source, project metadata, lockfile, `.env.example` and tests; exclude `.venv`, `.env`, caches and egg-info. Change the project package name/description and `SERVICE_NAME`, add domain routers, and keep its environment/virtualenv isolated. The `app` package name assumes one service per interpreter/process, matching the planned independent containers.
