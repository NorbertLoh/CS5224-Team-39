# Reset the AWS demo at `/reset`

RF57 provides a platform-admin confirmation page at `/reset`. Opening the URL
does not change anything. Sign in as `platform@example.test`, type `RESET DEMO`
and submit. The identity API authorizes the request and starts one fixed ECS
Fargate task using its task role. School operator credentials are not stored in
the browser or application; their expiry does not supply the task's credentials.
The lab and its workload roles must still be available.

## Dataset and reset scope

The requested seed is shared with the local RF07 accounts tool through
`dev/demo_seed/requested_seed.py`:

| Email | Application role |
| --- | --- |
| `patient@example.test` | Patient |
| `lohnorbert@gmail.com` | Patient |
| `doctor@example.test` | Dr. Tan, assigned to Meridian, verification pending |
| `clinic@example.test` | Meridian clinic administrator |
| `platform@example.test` | Platform administrator |

Both patients have the requested Temasek Boulevard address and the configured
private Singapore phone. Meridian Health Partners has its SGD 30 fee, branding
and Raffles Place pickup details and is **pending review**. Dr. Tan has a **pending**
doctor application with the shared fictional licence PDF. Clinic assignment does
not bypass doctor verification. There are no appointments, clinical records,
payments, orders or issued documents.

The user explicitly requested overwriting without a backup. This operation does
**not** create snapshots, dump files, backup archives or a restore checkpoint.
Existing RDS automatic backup and S3 versioning settings remain infrastructure
settings; this feature does not change them or depend on them for recovery.

The worker replaces rows in the nine application schemas while retaining their
tables, constraints and Alembic markers. The new rows and their verification are
one PostgreSQL transaction. An error during that transaction rolls it back. This
is not an undo operation after a successful commit. Old event queues and dedicated
Redis database 0 are cleared; their contents are not recoverable by transaction
rollback. External Stripe/courier activity is not refunded, cancelled or undone.
Use this only for the dedicated synthetic demo, between demonstrations.

Existing seeded Cognito users, passwords, Cognito subjects and application subject
IDs are preserved. Missing seed users are created with delivery suppressed, using
the private configured initial password. Disabled/unverified seed accounts are
refused. Other Cognito accounts and existing S3 objects are not deleted; application
rows referring to old records are removed. Existing provider configuration,
Cognito pools/clients, service secrets and infrastructure remain in place. The
operator's seeded account must survive the reset or the worker refuses it.

## Enable once

1. Build/publish the updated identity image through the existing release flow.
   The document image already supplies boto3, psycopg and ReportLab for the worker;
   reset code and the shared fixture are embedded in its task definition.
2. In the **existing** `infra/envs/demo` operator inputs set
   `enable_demo_reset = true`. Retain the existing images and other inputs. Review
   the Terraform plan before applying through the normal deployment process.
   The default is false; production/reference roots do not enable this capability.
3. Populate the new Secrets Manager secret `<name-prefix>/demo-reset/seed` with:

   ```json
   {
     "patient_phone": "<the requested private +65 phone>",
     "new_account_password": "<initial password for missing seed accounts>"
   }
   ```

   Use an ignored JSON file with the AWS CLI's `--secret-string file://...` or the
   Secrets Manager UI. Do not put values in Terraform, build variables or git.
   Existing confirmed users' passwords are not changed. A missing or invalid
   phone/password fails before the application is taken offline.
4. Keep the existing seeded `platform@example.test` login. Enabling reset disables
   the old four-account automatic seed provisioner, because it would recreate the
   old approved clinic on subsequent releases. Do not invoke the old
   `dev/release/seed-demo.mjs` after switching to this seed.
5. Publish the frontend build. The existing CloudFront SPA fallback serves `/reset`;
   no new public API service or URL rewrite is required. Visit it and confirm only
   when the demo's current data may be discarded.

Deployment itself never performs a reset. No new database migration is needed.
The reset task is separate from API startup and Terraform apply.

## Permissions and operation

Identity may read/write the one private S3 operation-state object, launch only the
fixed reset task in its own cluster, and pass only its execution/task roles to ECS.
It has no master DB secret or reset Cognito privileges. The worker has scoped
access to the reset state, seed/master secrets, the demo pool's user-provisioning
operations and the ten demo SQS queues. It has no RDS snapshot permissions.
Both use SDK task-role credentials. One S3 conditional write claims an operation;
retries reuse the request UUID as ECS's idempotency token. GET only reads status.

The worker validates the AWS account and deployment, obtains an advisory lock,
and temporarily inherits the service-owned DB roles using the bootstrap's RDS
administrator. This exceptional maintenance operation crosses service schemas;
ordinary APIs and workers retain their independent service ownership. It sets
the nine service roles to `NOLOGIN`, terminates their DB connections, waits 150
seconds for in-flight work to finish, purges the queues and waits for purge
completion. It then replaces/verifies rows, clears the dedicated TLS Redis cache,
restores service logins and removes its temporary role memberships.

The frontend keeps polling through temporary DB/API failures. The operation
normally takes several minutes plus ECS task startup. Existing application DB
pools reconnect once service logins are restored. No real provider transaction or
email is intentionally sent by the seed. Already submitted external events and
provider callbacks are outside the reset transaction and may arrive afterward;
do not run reset during active payment, delivery or release work.

The project's school account must allow the new task role, scoped `iam:PassRole`
and runtime operations. If it does not, the feature cannot be enabled merely by
deploying the frontend. The page reports disabled environments and preserves the
same queued request for launch retries instead of creating another reset.

## Failure recovery

Worker errors expose only their type; credentials and phone values are not sent
to the page. The latest private `reset/state.json` includes request/actor IDs,
stage, error type and a `roles_quiesced` indicator. Inspect the `demo-reset`
container's stream in the existing document CloudWatch log group.

Ordinary exceptions restore service `LOGIN` privileges in `finally`. A hard task
kill, expired/revoked workload access, or DB/network failure can prevent cleanup.
If the API cannot reconnect, an operator must use the existing bootstrap/master
access to restore `LOGIN` for identity, tenant, scheduling, consultation,
clinical_records, billing, fulfilment, document and notification. Remove only the
temporary memberships granted by the reset to that administrator. Confirm no
reset task is running and inspect the database before marking the private state
failed. Never clear an active claim merely to bypass the lock.

There is no reset-created backup to restore. A failed replacement transaction
retains the preceding database rows; a completed replacement is the new data.
After repairing a failure, another explicitly confirmed reset can rebuild the
requested seed. Restoring older data requires an independently available recovery
source and an operator-led procedure.

## Verification

- Identity tests cover authentication, platform-only authorization, the retained
  operator account, disabled configuration, confirmation validation, target
  injection, read-only GET, conditional claims and idempotent/ambiguous launches.
- Offline runner checks cover invalid targets/configuration, preserved passwords
  and IDs, queue failure, seed rollback and restoration of service logins.
- The disposable PostgreSQL CI job applies all nine service migration histories,
  runs the seed twice, checks the five accounts/two pending applications and
  migration markers, exercises constraint rollback, and verifies an external
  foreign key blocks reset rather than causing a cross-schema cascade.
- Terraform mock tests cover demo-only wiring, the fixed task permission and
  absence of snapshot permissions. Frontend lint, typecheck and build cover the
  new route and page.

Local/mocked verification is not deployed AWS evidence. Live task-role permissions,
RDS role administration, task execution, reconnection and the school lab's
credential lifecycle require an explicit disposable-demo deployment check.
