# Local development support

F09-F16 add Compose dependencies, proxy configuration, Floci bootstrap, Cognito test users, synthetic fixtures and persistence checks. Keep generated runtime data under ignored `.local/` or managed Docker volumes.

F09 supplies the root `compose.yaml` and `.env.example`; see [local setup](../docs/local-development.md). PostgreSQL/Redis are shared local dependencies, and the offline profile also runs Floci. Bootstrap, fixtures and proxy configuration remain later tasks.
