# W10 SES demo recipient permissions

Issue #386. The deployed dispatch-role test returned `AccessDenied` for
`ses:SendEmail` on a verified recipient identity. Both sender and recipient
verification succeeded. Existing failed jobs have no provider acceptance ID.

Add explicit verified recipient identity ARNs to the background-jobs module,
pass the optional list through demo-platform and the existing demo root, and
restrict the additional permission to the configured sender's From address.
Keep the default recipient list empty. Do not create competing state or replay
failed/uncertain jobs as part of the policy deployment.

Validate Terraform and the recipient/sender authorization boundary, inspect the
account-specific demo plan, apply the scoped IAM update, and complete the
user-authorized single plain-text delivery test. Provider acceptance is distinct
from inbox delivery. SES remains in sandbox mode.

Set `ses_recipient_identity_arns` in the ignored demo operator tfvars to the exact
regional identity ARN of each already-verified test recipient. The default is an
empty set; adding an ARN does not create or verify a mailbox. The background-jobs
module rejects wildcard and foreign-account/region identities. Its additional
recipient grant permits `SendEmail` and `SendRawEmail` only when `ses:FromAddress`
matches the configured sender mailbox identity. Sender permissions are preserved.

Apply through the existing `infra/envs/demo` backend with the deployed image pins.
No image rebuild, migration, queue replay, failed-job reset or production-access
request is required. Failed jobs with no retry time remain failed after this IAM
change; resend individual known-rejected notifications only when explicitly
requested. Never reset `uncertain` jobs without checking provider acceptance.

## Verification on 6 November 2026 (Singapore)

Six background-jobs mocked Terraform tests passed, including positive recipient
permission, sender restriction, wildcard rejection and foreign identity rejection.
The module and demo root validate; formatting and diff checks pass.

The reviewed demo plan changed the notification-dispatch inline policy and the
existing CloudFront optional-field normalization only (0 add, 2 update, 0 destroy).
Terraform apply succeeded without image, task-count, database or capacity changes.
IAM simulation allows both SES send APIs for the approved recipient with the
configured sender and returns `implicitDeny` when that recipient is used as From.

A temporary isolated Lambda used the deployed dispatch role and its VPC settings.
Before the fix SES returned `AccessDenied` on the verified recipient identity;
after the fix SES accepted the user's one authorized plain-text test and returned
a message ID. The temporary function was deleted. This proves provider acceptance
through the actual role; inbox receipt awaits the user's confirmation. No receipt
attachment test or historical notification replay is claimed.

Operator evidence remains ignored under `.local/email-role-diagnostic/`,
`.local/email-diagnostic-result.json`, `.local/w10-plan.json` and
`.local/w10-apply.log`. Issue #386 remains In progress pending review/merge and
completion criteria. PR #387 tracks this change.
