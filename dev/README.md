# Local development support

Root Compose runs the local dependencies and template API. `floci/bootstrap.sh` seeds the document bucket and synthetic provider secrets, then `floci/events.sh` configures the event bus, consumer queues/rules and DLQs. Run both with `docker compose --profile offline run --rm bootstrap`. See [local development](../docs/local-development.md) for resource names, queue URL handling and safe reruns. Cognito, workflow fixtures and full persistence checks remain F13-F16. Keep generated runtime data under ignored `.local/` or managed Docker volumes.
