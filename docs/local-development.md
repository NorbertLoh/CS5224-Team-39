# Local development setup

Status: the [F03 service template](../services/template/README.md) runs locally without external dependencies. Full local stack setup remains a placeholder until Compose/bootstrap tasks are implemented.

## Setup tasks

- F03-F05: FastAPI template, database migrations and container build.
- F06-F08: frontend scaffold, routes and API client.
- F09-F10: Compose dependencies and reverse proxy.
- F11-F13: Floci storage, messaging and Cognito bootstrap.
- F14/F16: fixtures, reset commands and validated pinned emulator release.

## Instructions to fill in

Record validated Node/Python versions, Docker Desktop/Linux-container requirements, environment file creation, build/start commands, service URLs, bootstrap/seed/reset commands and troubleshooting. Distinguish host URLs from container URLs and offline mode from cloud-connected mode.

Use only synthetic users and records. Do not document real passwords or API keys. Destructive resets must identify the exact local data/volume targets and avoid shared AWS data.
