# A01–A03 authentication

Merged PR #49 completes browser PKCE login, session renewal/logout,
and reusable FastAPI access-token verification; issues #46–#48 are closed.
F16's authentication dependencies are ready. Its wider API and persistence
results are recorded in [Floci verification](floci-verification.md).

## Local setup

Start and seed the pinned emulator from the repository root:

```powershell
docker compose --profile offline up -d floci
docker compose --profile offline --profile bootstrap run --rm bootstrap
```

Copy the printed `COGNITO_USER_POOL_ID`, `COGNITO_CLIENT_ID` and
`COGNITO_ISSUER` into the root `.env`. These are public configuration, not
credentials. Copy `apps/web/.env.example` to `apps/web/.env.local`, set
`VITE_COGNITO_CLIENT_ID` to the printed client and `VITE_COGNITO_ISSUER` to the
printed issuer. Keep the two localhost OAuth/API URLs from the example.
Restart Vite after changing its environment:

```powershell
cd apps/web
npm ci
npm run dev -- --host localhost
```

Use **http://localhost:5173/**. Callback `/auth/callback` and logout `/` are
registered by F13. `127.0.0.1` is a different origin and requires its own exact
callback/logout/CORS configuration. Root `COGNITO_CORS_ORIGINS` allows only
`http://localhost:5173` by default. Recreate Floci after changing that setting.
When changing ports, update callback, logout and CORS origins together.

Sign in with a seeded `patient@example.test`, `doctor@example.test`,
`clinic@example.test` or `platform@example.test`; synthetic password is
`LocalDemo123!`. The auth controls do not assign application roles or tenant
membership; A04–A06/U05 implement those checks and navigation.

For a container API with authentication configured:

```powershell
docker compose -f compose.yaml -f compose.auth.yaml --profile offline up -d --build template
```

The overlay uses the browser issuer verbatim while fetching JWKS through
`http://floci:4566/<pool>/.well-known/jwks.json`. It requires all three bootstrap
values. The base Compose remains usable for health-only scaffolding; protected
routes return 503 when authentication is unconfigured. Set the following for
a host API instead, then run `python -m app` in `services/template`:

```text
SERVICE_ENVIRONMENT=local
SERVICE_AUTH_ISSUER=<printed COGNITO_ISSUER>
SERVICE_AUTH_CLIENT_ID=<printed COGNITO_CLIENT_ID>
SERVICE_AUTH_JWKS_URL=<printed COGNITO_ISSUER>/.well-known/jwks.json
```

Install from `services/template/requirements.lock.txt` for the new PyJWT/RSA
dependencies. Service routes opt in with `Depends(require_principal)` from
`app.auth`. `/auth/session` is a small protected verification probe, reachable
through Vite as `/api/v1/template/auth/session`. Use `readSession()` from
`src/auth/session` with F08's `apiFetch(path, { accessToken })` when adding
protected feature requests. Health endpoints remain public.

## Session and validation behavior

Login uses random state and a 256-bit verifier with S256 PKCE, no client secret.
The callback consumes one pending transaction within ten minutes, checks state,
exchanges the code once, then strips the callback query from browser history.
React StrictMode shares the single callback exchange. Access/refresh tokens live
only in tab-scoped sessionStorage, survive reloads and clear at logout. No tokens
are rendered or logged. Browser claim checks detect configuration errors; the
API verifies signatures. As with any browser token storage, XSS can expose tokens.

The UI refreshes within 60 seconds of expiry, checks every five seconds and on
window focus, and shares concurrent refreshes. A failed refresh clears the
session/query cache and asks the user to sign in again. An in-flight refresh
cannot restore credentials after logout. Logout clears local credentials and
query data, attempts refresh-token revocation, and redirects through hosted
logout to clear the login cookie. A revocation outage still signs out locally
and displays a warning on return.

FastAPI accepts only RS256 signatures from configured JWKS, with exact issuer,
expiry/issued-at, nonempty subject, `token_use=access`, matching `client_id`, and
optional `SERVICE_AUTH_REQUIRED_SCOPES` (space separated). ID tokens are rejected;
their `aud` is not a substitute for the access-token client claim. Missing or
invalid tokens receive 401, insufficient scope 403, unavailable/unconfigured
JWKS 503. Keys are cached for five minutes and refreshed for an unknown key ID.
Local JWKS URLs never rewrite the token issuer. Non-local environments reject
emulator issuers and JWKS at startup and require an AWS Cognito issuer with its
matching HTTPS JWKS endpoint. Authentication does not grant tenant access.

## Verified Floci 2.2.0 behavior and F16 handoff

Verified 13 October 2026 with the real pinned container and seeded users:

- All four roles: browser authorization/S256 login, callback cleanup, reload,
  authenticated FastAPI probe and hosted logout succeeded.
- Direct live check: one-time code replay rejected; access tokens accepted;
  ID tokens rejected; Cognito refresh succeeded; revoked refresh rejected;
  next authorization after logout showed the sign-in form.
- Browser renewal succeeded after advancing the stored renewal deadline;
  invalid callbacks and invalid refresh tokens produced signed-out expiry UX.
  The browser clock/deadline check accelerates the UX test; signature expiry is
  independently tested with signed expired tokens in backend tests.
- OAuth `grant_type=refresh_token` returned **400**. The frontend deliberately
  uses `InitiateAuth` / `REFRESH_TOKEN_AUTH`, retaining the original refresh
  token when the response omits a replacement. That API refresh produces API
  sign-in scopes, rather than preserving the original OAuth scope list. Do not
  configure required OAuth scopes on this local flow without verifying them.
- Hosted logout clears the cookie but does not itself revoke tokens. Explicit
  `RevokeToken` rejects later refresh. Offline JWT verification cannot detect
  revocation of already-issued access tokens; they remain valid until expiry.
  **F16 found that revocation is lost on restart in Floci 2.2.0**: its persisted
  token store fails to deserialize, so previously revoked refresh tokens become
  usable again. This is a recorded blocker, not verified AWS behavior.

Floci does not apply refresh-token rotation and keeps hosted login sessions in
memory. F16 verified retained resources/keys and access/refresh token use across
restart/recreation; the hosted cookie required sign-in again. Real Cognito rotation, recovery/MFA,
revocation enforcement and connected-profile flows still need AWS verification.
See [pinned Floci documentation](https://github.com/floci-io/floci/blob/2.2.0/docs/services/cognito.md)
and [Cognito access-token claims](https://docs.aws.amazon.com/cognito/latest/developerguide/amazon-cognito-user-pools-using-the-access-token.html).

Run the simple patient smoke check with the configured host/container API running.
It checks PKCE login, authenticated API access, refresh and logout; the earlier
four-role compatibility findings above record the original verification.

```powershell
$env:COGNITO_CLIENT_ID='<printed client ID>'
services/template/.venv/Scripts/python.exe dev/floci/check_auth.py
```

The smoke check uses the standard localhost ports (Floci 4566, frontend 5173,
API 8000) and needs only `COGNITO_CLIENT_ID`. It uses the synthetic patient,
revokes only the refresh token it creates, never prints tokens, and preserves
seeded resources. It does not repeat the four-role/rejection/compatibility matrix.

Verification: frontend lint/type/build and 14 passing tests; backend Ruff and
19 passing service/authentication tests; real browser checks for all four roles
against both the host API and the built, healthy API container. CI runs the
frontend tests and focused backend authentication tests. The database integration
test is skipped without its dedicated database URL, unrelated to A01–A03.

Suggested follow-up: audit/restore the F07 role router, which is recorded as
complete but absent from the current frontend tree. This PR adds only the
authentication callback and controls rather than recreating role portals.
