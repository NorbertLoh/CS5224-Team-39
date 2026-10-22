# Full local application with Docker Compose (F17)

Use Docker Desktop with Linux containers and Compose **2.30 or newer**. No host
Python, virtualenv, Node or Stripe CLI is required. Run commands from the repository
root in PowerShell. The original host launcher, `dev/local_stack.ps1`, remains available.

## First setup

```powershell
./dev/compose.ps1 setup -Payments
```

Setup builds separate images for all nine Python services, the frontend and
signalling; starts PostgreSQL, Redis and Floci; runs the existing AWS-resource and
Cognito bootstrap; generates ignored configuration; provisions service-owned
schemas; runs each service's migrations explicitly; provisions the four real local
accounts; and starts APIs and workers. Repeating setup preserves service secrets,
profiles, memberships, application rows and Docker volumes. Migrations are never
part of API replica startup.

The launcher builds images in batches of two to reduce memory pressure on Windows.
Dependencies reach health before image builds begin. PostgreSQL runs with an init
process, a direct health probe and a 60-second shutdown grace period; these avoid
the [orphaned shell-probe restart issue](https://github.com/super-productivity/super-productivity/pull/9917)
and allow clean database shutdowns. Its startup health window also permits slow
cold recovery on Docker Desktop.

The billing API needs an actual Stripe **test** key and an active clinic's connected
account mapping to pass readiness. Keep these in ignored `services/billing/.env`
before setup, using its existing guide and `.env.example`:

```dotenv
SERVICE_STRIPE_SECRET_KEY=sk_test_REPLACE_LOCALLY
SERVICE_STRIPE_DESTINATIONS={"YOUR_ACTIVE_CLINIC_UUID":"acct_REPLACE_LOCALLY"}
```

Existing `STRIPE_SECRET_KEY` and `STRIPE_CONNECTED_ACCOUNT_ID` values are also
accepted: setup maps that account to existing active local clinics. No provider
credentials are fabricated. On a fresh database, configure the clinic through
identity/tenant APIs first and update the mapping, then rerun setup. Without billing
credentials/mapping its readiness remains 503; identity, tenant and the frontend
can run while that configuration is completed. `-Payments` adds the containerised
Stripe listener and obtains its signing secret before billing starts. It does not
create a Checkout Session or make a payment.

For delivery, existing Lalamove sandbox settings in `services/fulfilment/.env` are
imported. The location/contact JSON files must be under the repository's ignored
`.local/` directory; setup copies only those files into `.local/compose/delivery/`
and mounts them read-only at `/delivery`. The API fails closed for unavailable
provider/address configuration; no fixture adapter is enabled.

## Adopt this machine's existing host database

For a database previously started by the clinic/I01/I02 host guides:

```powershell
./dev/compose.ps1 setup -UseExistingDatabase -Payments
```

This checks `telelink-clinic-postgres`, stops the host launcher and the legacy
signalling stack, stops that PostgreSQL container, and mounts its **existing**
PostgreSQL 17 volume in the Compose `postgres` service. It records the external
volume reference and local administrator configuration under `.local/compose/`.
The legacy database container is retained, stopped. Never start both database
containers against the same volume. Subsequent commands automatically reuse the
adoption file; do not delete it while using the adopted database.

Floci remains the existing root Compose service and volume, preserving Cognito
subjects, S3 documents, event routes and queues. Application data is not copied
into a new database. The schema provisioner creates only missing roles/schemas;
it never drops or resets existing data.

To return to the host launcher: run `./dev/compose.ps1 down`, start
`telelink-clinic-postgres`, then use `dev/local_stack.ps1 start` with the host Stripe
CLI path. The existing service `.env` files are read as setup inputs and are not
rewritten by this workflow.

## Daily use

```powershell
./dev/compose.ps1 up -Payments
./dev/compose.ps1 check
./dev/compose.ps1 status
./dev/compose.ps1 logs
./dev/compose.ps1 down
```

Startup waits for API readiness and the browser entry point before launching the
workers, reducing contention on a busy development machine.

Open **https://localhost:8443**. Caddy uses a development CA; export its public root
certificate if needed for your dedicated development browser:

```powershell
docker compose -f compose.yaml -f compose.app.yaml cp tls:/data/caddy/pki/authorities/local/root.crt .local/compose/root.crt
```

No host certificate trust store is changed. Demo accounts are
`patient@example.test`, `doctor@example.test`, `clinic@example.test` and
`platform@example.test`, password `LocalDemo123!`. The setup command provisions
actual Cognito subjects and backend profiles; clinic membership is still managed
through the real APIs/UI, and Cognito groups do not grant application access.

`down` stops/removes application containers and networks, retaining all volumes.
The scripts never run `down --volumes`. Host API ports remain 8001–8007 and 8009,
Vite 5173, HTTPS 8443, Floci 4566 and PostgreSQL defaults to 55432. Stop the legacy
host APIs before starting Compose; setup handles this changeover automatically.

The included workers cover scheduling expiry/payment/publishing/resolution,
billing expiry/processing/publishing, records publishing, document generation and
publishing, fulfilment payment consumption, delivery submission/resolution/
publishing/tracking, and notification intake/dispatch. Notification SES calls
target Floci's local capture store.

## Development reload

```powershell
./dev/compose.ps1 up -Payments -Development
```

`compose.dev.yaml` adds read-only source mounts and Uvicorn reload for the APIs,
plus Vite source mounts/polling. Workers use the mounted code but must be restarted
after edits. Dependency or migration changes need a rebuild and explicit setup/
migration run. Production Python images install locked dependencies and the shared
package, use an unprivileged user and contain no `.env` or virtualenv from the host.
Each service keeps its own image, entry point, schema and migrations.
The frontend image preserves the shared contracts and development fixtures in
their repository-relative locations and runs the TypeScript and production build
checks. Development mode mounts those shared directories as well.

## Raw Compose commands and configuration

The PowerShell wrapper only orchestrates Docker. The equivalent files are root
`compose.yaml` plus `compose.app.yaml`, optionally `compose.dev.yaml` and the
generated database adoption override.

Image builds run in pairs through a generated Bake definition file. This avoids
the intermittent Compose/Bake closed-stdin error described in
[Docker Compose #13243](https://github.com/docker/compose/issues/13243).

For example, after setup on this machine:

```powershell
docker compose --env-file .local/compose/compose.env -f compose.yaml -f compose.app.yaml -f .local/compose/database.yaml --profile payments ps
```

Omit the last file on a fresh setup. `setup` and `bootstrap` are explicit one-shot
tools; their profiles are not part of normal startup. To migrate one service:

```powershell
docker compose --env-file .local/compose/compose.env -f compose.yaml -f compose.app.yaml -f .local/compose/database.yaml run --rm --no-deps scheduling python -m alembic upgrade head
```

Generated `.local/compose/*.env` files contain local secrets and provider sandbox
values and stay ignored by Git. Normal startup reads these generated files; rerun
setup after changing its host `.env` inputs. Do not post rendered Compose output
or raw provider logs, since they can contain credentials.

The browser keeps the public Cognito issuer `http://localhost:4566/<pool>` while
APIs fetch JWKS through `http://floci:4566`. Service calls use Compose DNS, and
document signatures are created with the browser-facing `http://localhost:4566`
endpoint itself, preserving SigV4 rather than rewriting signed URLs. HTTPS/WSS
uses one browser origin; internal API routes remain blocked by the Vite proxy.

## Verification

`check` probes all eight API readiness endpoints and the frontend, then performs
PKCE sign-in and an authenticated profile read for all four local accounts. Also
check `status` and worker logs for restarts; a running process alone does not prove
that it processed an event.

Journey checks are documented in [I01](I01-local-journey.md),
[I02](I02-local-journey.md) and [Q02](Q02-booking-verification.md). Compose packaging
does not complete I03–I05, external-network TURN or AWS deployment. Record the
actual container verification evidence in the F17 PR.
