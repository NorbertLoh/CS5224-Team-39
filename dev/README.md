# Local development support

Root Compose runs the local dependencies and template API. `floci/bootstrap.sh` seeds the document bucket and synthetic provider secrets through `docker compose --profile offline run --rm bootstrap`. See [local development](../docs/local-development.md) for startup, resource names and rerun behaviour. Cognito, messaging, workflow fixtures and full persistence checks remain F12-F16. Keep generated runtime data under ignored `.local/` or managed Docker volumes.
