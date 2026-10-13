# F16: Floci compatibility and persistence

Verified on 13 October 2026 using released Floci **2.2.0**, Linux amd64 on
Docker Desktop. A revoked refresh token becomes usable after restart because
Floci cannot reload its revocation store. The user accepted keeping Floci with
documented local limitations and tracking real AWS verification separately in
[issue #54](https://github.com/NorbertLoh/CS5224-Team-39/issues/54).
AWS verification has not been performed. PR #53 remains unmerged;
issue #43 stays In progress and the backlog stays unchecked.

The Compose default and environment example pin the tested multi-platform
manifest `sha256:e97cd0c1dc2aa14e7697fb5ef5018404c4d6345169dbd276315f0bed2c7b0520`.
It contains amd64 and arm64 images; arm64 was not tested. Existing `.env`
image overrides take precedence, so update `FLOCI_IMAGE` when adopting this pin.
See the [2.2.0 release](https://github.com/floci-io/floci/releases/tag/2.2.0).

## Results

Checks used project `telelink-f16`, ports 4567/8001/5183 and volume
`telelink-f16_floci_data`. Persistence comparisons used only this verification volume.
The baseline was compared after a graceful restart and then after removing
and recreating the containers/network with the same volume. **Bootstrap was
not run between these comparisons.**

| Service | Operations checked | Retained across both lifecycle checks |
| --- | --- | --- |
| S3 | Bucket/public-access-block reads, object put/get, signed download | Object bytes and all four public-access-block settings |
| Secrets Manager | Seeded secret reads; fresh secret create, new version and read | Both seeded values and version IDs |
| SQS | Queue create/attributes, send/receive, visibility change, delete | Ten queues' relevant attributes/policies; pending probe/DLQ messages and six workflow events |
| EventBridge | Bus/rule/target reads and `PutEvents` | Bus/rule ARNs, patterns, states, targets, retry and delivery-DLQ settings |
| Cognito | Pool/client/user/group reads, discovery/JWKS, browser PKCE, SDK refresh and revocation | Pool/client IDs/config, four users' subjects/status/groups, issuer/discovery and signing keys; **revocation reload fails** |
| SES | Identity verification/read, `SendEmail`, local mailbox inspection | Verified identity and captured message ID/body/timestamp |

After recreation, a prebuilt SDK runner on an **internal Docker network**
passed the same state comparisons and delivered all six fresh workflow
events with distinct correlation IDs and matching payloads. New object writes,
secret versions and captured email also succeeded. No container internet access
was needed for these operations. Build/download the runner and service images
before this disconnected phase.

All four browser roles passed PKCE return/query cleanup, reload, authenticated
API access, refresh/logout and expiry UX before and after the first restart.
Tokens issued before restart still refreshed and passed the fresh API verifier
after recreation, using container-facing JWKS and the unchanged browser issuer.
The original hosted-login cookie required sign-in again after restart.

## Reproduce the service checks

Use a fresh disposable `telelink-f16` project/volume. The helper is intentionally
limited to localhost port 4567 or `floci:4566` inside that project's network.
It uses explicit dummy credentials and synthetic data. Start from the repo root:

```powershell
$env:FLOCI_PORT='4567'
$env:TEMPLATE_HOST_PORT='8001'
$env:COGNITO_CALLBACK_URL='http://localhost:5183/auth/callback'
$env:COGNITO_LOGOUT_URL='http://localhost:5183/'
$env:COGNITO_CORS_ORIGINS='http://localhost:5183'

docker compose -p telelink-f16 --profile offline up -d --wait floci
docker compose -p telelink-f16 --profile offline run --rm bootstrap
docker build -f dev/floci/Dockerfile.checks -t telelink-f16-checks .
New-Item -ItemType Directory -Force .local | Out-Null
docker run --rm --network telelink-f16_default -e F16_ENDPOINT=http://floci:4566 -v "${PWD}:/workspace:ro" -v "${PWD}/.local:/workspace/.local" telelink-f16-checks prepare

docker compose -p telelink-f16 --profile offline restart floci
docker compose -p telelink-f16 --profile offline up -d --wait floci
docker run --rm --network telelink-f16_default -e F16_ENDPOINT=http://floci:4566 -v "${PWD}:/workspace:ro" telelink-f16-checks check

# Recreate on a network without internet access; retain the volume.
docker compose -p telelink-f16 --profile offline down
docker compose -p telelink-f16 -f compose.yaml -f dev/floci/compose.offline-check.yaml --profile offline up -d --wait floci
docker run --rm --network telelink-f16_default -e F16_ENDPOINT=http://floci:4566 -v "${PWD}:/workspace:ro" telelink-f16-checks check
docker run --rm --network telelink-f16_default -e F16_ENDPOINT=http://floci:4566 -v "${PWD}:/workspace:ro" telelink-f16-checks exercise
```

`prepare` exercises APIs, publishes the six contract fixtures and saves the
synthetic baseline under ignored `.local/f16-state.json`. `check` compares
resources and reads pending messages without deleting them. It advances SQS
receive counts: the prescribed sequence reads consumer messages three times,
including preparation. Extra checks can eventually redrive those messages.
Run `exercise` last; it adds fresh test data, so subsequent baseline comparisons
are no longer expected to match. Do not rerun `prepare` after restart to conceal
missing state. Use a fresh disposable volume for a new complete run.

No existing `.local` files or Python virtual environment are required. The
commands above create the directory and run the committed scripts in the SDK
image. `prepare` generates the baseline for your own emulator; `check` reads
that baseline after restart. The optional revocation repro below generates its
own token file. Keep both files untracked: they contain runtime IDs, synthetic
secret values and a refresh token, and cannot serve as another teammate's
baseline. The application and bootstrap do not depend on these files.

An internal-only Docker network also blocks host access to the published ports
in the tested Docker Desktop setup. The runner therefore connects directly to
`floci:4566`; it rewrites host-facing queue URLs for that connection.
Stop the test project with the same `-p telelink-f16`/Compose files; `down`
preserves the verification volume. Reset instructions are in
[local development](local-development.md#check-and-stop); never reset another
project's volume.

## Reproduce authentication checks

Do these before switching to the internal-only network. Copy the bootstrap's
public `COGNITO_USER_POOL_ID`, `COGNITO_CLIENT_ID` and `COGNITO_ISSUER` into the
shell, then start the API using `compose.auth.yaml` with the same project/ports.
For Vite use client/issuer from this pool, OAuth base
`http://localhost:4567/cognito-idp`, API URL `http://localhost:4567/`,
`TEMPLATE_API_TARGET=http://127.0.0.1:8001` and port 5183.
See [authentication setup](authentication.md) for the environment names.

Walk through all four seeded roles at `http://localhost:5183/`. Verify sign-in,
query cleanup, reload, API access and sign-out, then repeat after restart.
For a retained-session test, keep a signed-in tab across restart and trigger
renewal; the access/refresh tokens should work, while a separate authorization
request carrying the old hosted cookie should show the sign-in form. Verify
API use with `GET /api/v1/template/auth/session` and a bearer access token.
Do not log tokens or commit browser session files.

### Accepted revocation persistence limitation

`RevokeToken` succeeds and refresh immediately fails with `NotAuthorizedException`.
After restarting without reseeding, the same refresh token is accepted again.
The startup log identifies the cause: persisted `RevokedTokenInfo` includes
the computed `expired` property, but its reader rejects that unknown field.
Floci quarantines `cognito-revoked-tokens.json` as `.corrupt` and loads an empty
revocation store. Signing keys remain unchanged. The persistent store creates
its own `ObjectMapper`; a Quarkus request-Jackson setting does not fix this
reader. The previous 2.1.0 release has the same relevant serializer/model code;
it was not substituted or claimed verified.

The small `check_revocation.py` repro reuses the patient's PKCE login helper,
stores only a synthetic token under ignored `.local/`, and fails if that revoked
token is accepted after restart. On the internal verification network:

```powershell
docker run --rm --network telelink-f16_default -e F16_ENDPOINT=http://floci:4566 -v "${PWD}:/workspace:ro" -v "${PWD}/.local:/workspace/.local" --entrypoint python telelink-f16-checks dev/floci/check_revocation.py prepare
docker compose -p telelink-f16 -f compose.yaml -f dev/floci/compose.offline-check.yaml --profile offline restart floci
docker compose -p telelink-f16 -f compose.yaml -f dev/floci/compose.offline-check.yaml --profile offline up -d --wait floci
docker run --rm --network telelink-f16_default -e F16_ENDPOINT=http://floci:4566 -v "${PWD}:/workspace:ro" --entrypoint python telelink-f16-checks dev/floci/check_revocation.py check
```

Expected: `check` passes. **Observed on 2.2.0: it fails with a revived token.**
This is an accepted local limitation; real Cognito verification is tracked in
[issue #54](https://github.com/NorbertLoh/CS5224-Team-39/issues/54).
The repro still reports the failure rather than claiming revocation persisted.
No JWT checks were weakened,
no persisted records were rewritten, and no patched emulator image was used.
Relevant pinned source:
[revocation model](https://github.com/floci-io/floci/blob/2.2.0/src/main/java/io/github/hectorvent/floci/services/cognito/model/RevokedTokenInfo.java),
[persistent reader](https://github.com/floci-io/floci/blob/2.2.0/src/main/java/io/github/hectorvent/floci/core/storage/PersistentStorage.java).

Verification also used the existing 12 focused backend authentication tests
for rejected signatures/issuer/client/expiry/token-use/scope and configuration
guards. Frontend and backend CI remain required before review.

## Known differences and remaining AWS checks

[Issue #54](https://github.com/NorbertLoh/CS5224-Team-39/issues/54) tracks the
Cognito lifecycle/revocation and private S3/document-download acceptance checks
for W05/W08/P03. It is future work and does not claim those tasks are complete.

- **S3 access control/expiry is not proven locally.** Under this configuration,
  unsigned and expired signed object GETs both returned HTTP 200, despite the
  stored public-access block. Signed URL generation/download works; it does
  not establish private access or expiry enforcement. Keep synthetic files and
  loopback bindings. W08/P03 and AWS integration must verify private bucket/IAM
  denial, valid downloads and expired/invalid URL rejection on real S3.
- **Cognito:** OAuth refresh returned 400; `REFRESH_TOKEN_AUTH` works but uses
  API sign-in scopes and retains the original refresh token. Rotation is not
  applied. Hosted sessions are in memory, while users, keys and refresh tokens
  survive restart. Hosted logout clears cookies; explicit revocation blocks
  refresh only until the next restart because of the blocker above.
  Stateless JWT verification accepts an issued access token until
  expiry. Real managed login, rotation, recovery/MFA and revocation enforcement
  remain W05/connected-profile checks. See [auth findings](authentication.md).
- **Queues/events:** this verifies SDK operations, persistence and six routes.
  It does not establish IAM enforcement, delivery-failure retries, worker
  idempotency, failed-job redrive or operator replay; those remain M03/M04 and
  real AWS integration. The pending DLQ marker is a direct send, not evidence
  of a worker failure reaching its DLQ.
- **SES:** captured synthetic email persists and new sends work without SMTP.
  There is no external delivery, sender ownership proof or AWS sandbox/quota
  validation here; those remain N01/W10.
- Graceful shutdown/recreation was tested; crash/power-loss durability,
  upgrades, load, backups and production AWS compatibility were not claimed.

Primary references: pinned [storage documentation](https://github.com/floci-io/floci/blob/2.2.0/docs/configuration/storage.md),
[Cognito documentation](https://github.com/floci-io/floci/blob/2.2.0/docs/services/cognito.md)
and [SES documentation](https://github.com/floci-io/floci/blob/2.2.0/docs/services/ses.md).
