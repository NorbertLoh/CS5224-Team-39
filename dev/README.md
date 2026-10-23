# Local development support

For repeatable synthetic demo data, see [the local demo seed](demo_seed/README.md).
Its default command is read-only preflight; explicit `--reset` backs up the
configured host stack before replacing local accounts and linked examples.

Use `refund_demo.py` to prepare a real Stripe sandbox consultation payment after
seeding; see [the repeatable refund demo](../docs/refund-demo.md). It keeps provider
transactions separate from the simulated seed and leaves refunds to clinic admins.

Root Compose runs the local dependencies and template API. `floci/bootstrap.sh` seeds the document bucket and synthetic provider secrets, then runs `events.sh` for messaging and `cognito.sh` for the public SPA client and four demo identities. Run all with `docker compose --profile offline run --rm bootstrap`. See [local development](../docs/local-development.md) for resource names, demo login configuration and safe reruns. [Shared workflow fixtures](fixtures/README.md) provide deterministic two-clinic data for mock UI/service development. [Authentication](../docs/authentication.md) covers login/session setup; [F16 verification](../docs/floci-verification.md) covers six-service API/persistence checks and the tested image pin. Keep generated runtime data under ignored `.local/` or managed Docker volumes.

`clinic_local.py` configures real local clinic APIs and explicit database-backed
local accounts; see [clinic backend setup](../docs/clinic-backend.md).

`local_stack.ps1` starts, checks or stops all implemented local APIs and workers
in the background; see [I02 local journey](../docs/I02-local-journey.md). This includes
payment confirmation, delivery submission/resolution/publishing/tracking, document
generation and notification intake/email capture. It reuses an already-running
`telelink-local-stripe-forwarder` Docker container, or starts the supplied Stripe CLI.

Before starting, install each service's virtualenv and migrate its schema, including
`notification`. Configure fulfilment's sandbox credentials, saved pickup/postcode
directory and synthetic contacts using [payment setup](../services/fulfilment/PAYMENTS.md)
and [delivery setup](../services/fulfilment/DELIVERIES.md). Configure notification's
four matching upstream keys and local Floci SES using [notification setup](../services/notification/WORKER.md).
All worker logs and PIDs are under `.local/stack/<name>.*`; `status` includes every
worker. A failed worker startup makes `start` fail rather than report success.

```powershell
./dev/local_stack.ps1 start
./dev/local_stack.ps1 status
./dev/local_stack.ps1 stop
```

`compose.ps1` runs all implemented services and workers in Docker, with explicit
setup/migrations, database adoption and development reload. See
[full-stack Compose setup](../docs/compose-stack.md).
