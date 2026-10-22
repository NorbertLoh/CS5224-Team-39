# Local development support

Root Compose runs the local dependencies and template API. `floci/bootstrap.sh` seeds the document bucket and synthetic provider secrets, then runs `events.sh` for messaging and `cognito.sh` for the public SPA client and four demo identities. Run all with `docker compose --profile offline run --rm bootstrap`. See [local development](../docs/local-development.md) for resource names, demo login configuration and safe reruns. [Shared workflow fixtures](fixtures/README.md) provide deterministic two-clinic data for mock UI/service development. [Authentication](../docs/authentication.md) covers login/session setup; [F16 verification](../docs/floci-verification.md) covers six-service API/persistence checks and the tested image pin. Keep generated runtime data under ignored `.local/` or managed Docker volumes.

`clinic_local.py` configures real local clinic APIs and explicit database-backed
local accounts; see [clinic backend setup](../docs/clinic-backend.md).

`local_stack.ps1` starts, checks or stops the full local I01/I02 stack in the background; see [I02 local journey](../docs/I02-local-journey.md).
It also starts the fulfilment payment consumer so verified medication payments
update orders from pending to paid. The worker uses the existing
[medication payment configuration](../services/fulfilment/PAYMENTS.md); its logs
are `.local/stack/fulfilment-payment-worker.out.log` and `.err.log`.

`compose.ps1` runs all implemented services and workers in Docker, with explicit
setup/migrations, database adoption and development reload. See
[full-stack Compose setup](../docs/compose-stack.md).
