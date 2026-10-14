# Real clinic backend

All implemented clinic pages use identity and tenant APIs. There is no frontend
demo mode. PostgreSQL owns profiles/memberships and S3 owns logos. Local development
uses real FastAPI services/PostgreSQL with Floci for Cognito/S3.

## First local setup (PowerShell)

Start Floci and bootstrap Cognito using [local development](local-development.md).
The helper below uses localhost:4566 and the existing four local accounts only.
It cannot target AWS. Run from the repository root with Docker Desktop available.

Create the Python environment if needed (Python 3.10+):

```powershell
python -m venv services/identity/.venv
services/identity/.venv/Scripts/python.exe -m pip install -r services/identity/requirements.lock.txt -r services/tenant/requirements.lock.txt
services/identity/.venv/Scripts/python.exe -m pip install --no-deps --no-build-isolation -e packages/python_common
```

Use a separate persistent development database; never point reset-enabled tests
at this database. These database credentials are local development values.
Create the container/schema once:

```powershell
docker run --name telelink-clinic-postgres -e POSTGRES_PASSWORD=clinic-local-admin -e POSTGRES_DB=telelink -p 127.0.0.1:55411:5432 -d postgres:17
docker exec telelink-clinic-postgres pg_isready -U postgres -d telelink
Get-Content -Raw services/identity/scripts/create-local-schema.sql | docker exec -i telelink-clinic-postgres psql -v ON_ERROR_STOP=1 -U postgres -d telelink
Get-Content -Raw services/tenant/scripts/create-local-schema.sql | docker exec -i telelink-clinic-postgres psql -v ON_ERROR_STOP=1 -U postgres -d telelink
```

Wait for PostgreSQL to accept connections before provisioning. On later runs use
`docker start telelink-clinic-postgres` and preserve its data.
Migrate each service-owned schema:

```powershell
$env:SERVICE_DATABASE_URL='postgresql+psycopg://identity:local-demo-only@127.0.0.1:55411/telelink'
Push-Location services/identity
.venv/Scripts/python.exe -m alembic upgrade head
Pop-Location
$env:SERVICE_DATABASE_URL='postgresql+psycopg://tenant:local-demo-only@127.0.0.1:55411/telelink'
Push-Location services/tenant
../identity/.venv/Scripts/python.exe -m alembic upgrade head
Pop-Location
Remove-Item Env:SERVICE_DATABASE_URL
services/identity/.venv/Scripts/python.exe dev/clinic_local.py
```

The helper creates missing service/frontend `.env` files and random local
inter-service/cursor keys under ignored `.local/clinic/`. Existing `.env` files
are preserved; update them manually if they contain older fixture configuration.
Identity uses `SERVICE_TENANT_URL`, not `SERVICE_CLINIC_FIXTURE_PATH`. Both services
must share matching tenant/identity keys, with separate cursor keys.
The helper explicitly provisions actual local Cognito subjects into PostgreSQL;
Cognito groups never grant backend roles. It creates a separate unversioned
branding bucket with public access blocked. Local public logos are streamed by
tenant's public branding endpoint; no browser reads the private bucket directly.

Start these in separate terminals:

```powershell
cd services/identity
.venv/Scripts/python.exe -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8001
```

```powershell
cd services/tenant
../identity/.venv/Scripts/python.exe -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8002
```

Optionally create a first database-backed clinic, approve it through the platform
API and add a doctor through identity's membership API:

```powershell
services/identity/.venv/Scripts/python.exe dev/clinic_local.py --create-clinic
cd apps/web
npm ci
npm run dev
```

Both `http://localhost:5173` and `http://127.0.0.1:5173` are registered for local
Cognito callback/logout and Floci CORS. For a different frontend port, register
its exact URLs and add its origin to `COGNITO_CORS_ORIGINS`. After changing CORS,
recreate Floci with `docker compose --profile offline up -d --wait floci`;
existing Cognito/S3 data stays in its persistent volume.
Open http://localhost:5173 and sign in as `clinic@example.test`, password
`LocalDemo123!`. The clinic is a persisted local database record, editable through
Manage clinics. It is not imported from the shared fixtures. Re-running the helper
preserves existing profile fields. Local accounts/passwords are for Floci only.

## Local versus AWS

Set these public frontend build variables in `apps/web/.env`:

| Setting | Local | AWS |
| --- | --- | --- |
| `VITE_USE_AWS` | `false` | `true` |
| API base | `VITE_LOCAL_API_BASE_URL=/api/v1` | `VITE_AWS_API_BASE_URL=https://<gateway>/api/v1` |
| Cognito values | `VITE_COGNITO_*` | `VITE_AWS_COGNITO_*` |

Each Cognito set needs `CLIENT_ID`, `ISSUER`, `OAUTH_BASE_URL`, `API_URL`.
AWS URLs must be HTTPS and use the deployed public Cognito client. Register the
frontend origin's `/auth/callback` and `/` as Cognito callback/logout URLs.
Restart Vite or rebuild after changes. API prefixes are `/identity` and `/tenant`.
AWS requires deployed services, PostgreSQL, gateway routing/CORS and Cognito;
the flag selects them but does not deploy infrastructure. No fake AWS URL is
provided and cloud integration has not been verified by this local check.

For AWS logos, configure tenant's `SERVICE_LOGO_BUCKET`,
`SERVICE_LOGO_PUBLIC_BASE_URL` (HTTPS CDN) and region; leave
`SERVICE_LOGO_S3_ENDPOINT` unset. Use an unversioned branding bucket and IAM access
for the service, plus CDN access to public clinic logos. Never reuse the clinical
documents bucket. See [tenant logo API](../services/tenant/docs/api.md).

## Staff management

Staff assignment accepts existing accounts' email addresses; memberships show
names and emails. For existing local databases, migrate identity and backfill the
four seeded accounts from Cognito:

```powershell
$env:SERVICE_DATABASE_URL='postgresql+psycopg://identity:local-demo-only@127.0.0.1:55411/telelink'
Push-Location services/identity
.venv/Scripts/python.exe -m alembic upgrade head
Pop-Location
Remove-Item Env:SERVICE_DATABASE_URL
services/identity/.venv/Scripts/python.exe dev/clinic_local.py
```

Restart identity after migration. The helper updates email mappings while preserving
display names, roles, memberships and clinic profiles. AWS operators must backfill
verified emails from their configured pool. Accounts without email remain editable
by ID; browser input cannot provision identities.

Open **Manage staff** from Manage clinics or the profile editor. The route is
`/clinic-admin/clinics/<tenant UUID>/staff`. Lists include active and revoked
memberships with cursor pagination. Use an existing identity subject UUID to
assign doctor, clinic administrator, or both roles. **Edit roles** replaces the
role set; **Revoke access** retains the row; **Reactivate** opens the role form
and **Save roles** restores active access. Saving waits for the backend response
and refreshes the membership and doctor lists. No runtime fixtures are used.

The membership API returns names/emails for authorized administrators and has no
account creation/search endpoint. Email assignment resolves an existing provisioned
account; subsequent edits use its stable subject ID. Authorization is enforced by
identity; the last active clinic
administrator cannot be demoted or revoked. Local identity must use
`SERVICE_TENANT_URL` with matching `SERVICE_IDENTITY_SECRET` in tenant; unset
`SERVICE_CLINIC_FIXTURE_PATH`. AWS uses the same API paths/configuration described
above; no additional frontend settings are required. Apply identity migration `0002`.

## Doctor directory

Public `GET /tenant/clinics/{tenant_id}/doctors` checks the clinic is active and
provisioned, then calls identity with a short-lived service token scoped to
`telelink-identity-doctors`. Identity returns only active doctor subject IDs and
display names, sorted by display name/ID with signed clinic-bound pagination.
Revocation affects the next request. Internal endpoints reject user tokens and
creator-provisioning tokens. Outages show retry errors, never fixture fallback.
