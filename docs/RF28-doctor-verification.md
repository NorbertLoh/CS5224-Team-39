# RF28 doctor applications and verification

Accounts remain shared. `/join-as-doctor` requires sign-in and preserves that
destination through signup/sign-in. The form collects name on licence, registration
number, licensing authority, specialty and one supporting PDF/PNG/JPEG (maximum
5 MiB; combine multiple pages into a PDF). Applicants see pending, approved or
rejected status; rejected applications can be corrected and resubmitted. Patient
permissions remain available independently.

Platform administrators use `/platform-admin/doctors`, also linked in role
navigation, to filter applications, download evidence, approve/reject with a review
note and read submission/review history. Rejection reasons are shown to applicants.
Self-review is denied. Submissions and decisions serialize on the applicant's
subject row; revision checks reject stale decisions and concurrent submissions.
Pending and approved applications cannot be edited by the applicant.

## Assignment and access

Clinic administrators can assign an existing account as doctor before application
or approval. Staff management shows **Pending verification — doctor access
disabled** until approval. Membership status remains active/revoked, independent
of verification; this avoids disabling a combined clinic-admin role while its
doctor role is pending.

Identity `/me` returns only effective roles: doctor requires an approved
application and active owning-clinic membership. A doctor-only unverified
membership is omitted; a combined membership retains clinic administration.
Identity access decisions use the same projection. The service-only public doctor
directory filters unapproved applications. Downstream services continue to use
their existing fresh identity lookups/access decisions, so direct requests cannot
bypass verification by selecting the doctor UI. Approval does not create a
membership or reactivate a revoked membership. No automatic licence validation is
performed; the platform reviewer must check the evidence.

## Persistence and deployment

Back up identity before deploying, then run identity Alembic **0005** before
starting the updated identity API. No new environment variables or other service
migrations are required. Deploy identity and web together. Readiness requires 0005.

Migration 0005 adds a stored `doctor_documents.filename`, using the doctor's name
and file type, for example `Jane Tan - licence.pdf`. New submissions use the name
on the licence; existing files are backfilled from their original submission or
account name. Downloads use that filename, including Unicode names. Historical
evidence retains its original name when reused on a resubmission. File names are
sanitized to remove path separators and control characters.

**Existing doctor assignments are unverified after deployment.** The migration
does not fabricate verification for existing or seeded accounts. Those accounts
must submit an application and receive platform approval to resume clinical access.
Patient and clinic-admin roles are preserved. Demo reset/seed tooling still creates
assignments but does not grant verification; use the same application/review flow
for seeded doctors. Automated downstream tests may explicitly arrange an approved
application as a test precondition.

The identity database owns the application, private binary supporting files and
append-only API submission/review snapshots (including the document identifier).
Evidence is served only to its owner or a platform administrator, as an attachment
with `no-store`, `nosniff` and a sandbox policy. Clinic administrators and other
doctors cannot read it. Historical evidence remains available to reviewers after
resubmission. Include these tables in database backup/access/retention practices;
there are no public object URLs. Downgrade refuses to discard saved applications,
documents or review history.

## Verification

Use a **disposable** PostgreSQL database with the identity schema and service role:

```powershell
$env:TEST_DATABASE_URL = 'postgresql+psycopg://identity:local-demo-only@127.0.0.1:55438/telelink'
$env:IDENTITY_TEST_ALLOW_RESET = '1'
# From services/identity, with its locked dependencies installed:
python -m pytest -q
python -m ruff check .
python -m ruff format --check .
```

The suite exercises application/rejection/resubmission and immutable evidence
history; unauthenticated/other-account/clinic-admin document denial; bounded and
type-checked uploads; stale/concurrent decisions and submissions; self-review
denial; pending access, approved-without-clinic, mixed roles, cross-clinic access,
revocation and the filtered doctor directory. Persistence tests exercise migration
upgrade/downgrade and model parity. Frontend verification uses lint, typecheck,
build, probe typecheck and the existing session synchronization checks.

3 November 2026 verification: all **174 identity checks**, Ruff/format, the
architecture guard, frontend lint/typecheck/build, probe typecheck and seven
session checks passed. Identity and web Docker images built successfully. The
existing local identity schema was backed up under ignored `.local/backups/`
before applying migration 0004; the updated identity service reports ready and
both new frontend routes return successfully. The disposable test PostgreSQL
container was stopped afterward. Browser interaction/layout acceptance is left
to the user at their request. AWS deployment and external licence validation
were not performed.
