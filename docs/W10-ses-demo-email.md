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
attachment test or historical notification replay was performed at that stage.

Operator evidence remains ignored under `.local/email-role-diagnostic/`,
`.local/email-diagnostic-result.json`, `.local/w10-plan.json` and
`.local/w10-apply.log`. Issue #386 remains In progress pending review/merge and
completion criteria. PR #387 tracks this change.

After the user separately authorized resending the latest consultation receipt,
a recovery task verified its ready receipt PDF, consultation payment and matching
patient/tenant ownership. It changed exactly one definitively rejected job back
to pending, preserving the previous attempt count and all other jobs. The normal
scheduled dispatcher accepted the receipt attachment through SES at 00:36:33
Singapore time on 6 November 2026. Its job is now `sent`, attempts 2, no error,
and has a nonempty provider message ID. The other five recent failed jobs remain
unchanged. Inbox delivery remains unconfirmed; the user had not seen the earlier
plain-text test. Virtual Deliverability Manager is not enabled, so SES message
insights cannot establish downstream Gmail delivery. No delivery feature was
enabled and no further emails were sent. Recovery evidence is kept in ignored
`.local/receipt-retry-*.json` and `.local/email-diagnostic-result.json` files.

## Delivery investigation after acceptance

The user reported that neither the plain-text test nor the retried receipt was
visible. Live checks found the recipient absent from the SES suppression list.
The sender identity is individually verified, but DKIM signing is disabled
(`NOT_STARTED`) and no custom MAIL FROM domain is configured. DNS for
`_dmarc.u.nus.edu` publishes `v=DMARC1;p=reject`. Consequently this SES sender
configuration has neither aligned DKIM nor aligned SPF for the NUS From domain.
This is a confirmed authentication configuration defect and a strong explanation
for downstream rejection; Gmail's actual SMTP result has not been obtained.

The account has no SES domain identities and no Route 53 hosted zones. Remediation
requires DNS access to a sender domain controlled by the team (or a separately
authorized authenticated mail provider). Do not switch to another consumer or
university mailbox and assume email verification supplies domain authentication.
The user has been asked for a controllable domain and the rejection text from
the NUS sender inbox, where SES bounce forwarding is enabled. No further messages
were sent. W10 remains In progress; domain access and inbox evidence are blockers.

Reference: https://docs.aws.amazon.com/ses/latest/dg/send-email-authentication-dmarc.html

## User-selected Gmail demo sender

The school-recipient bounce subsequently confirmed `550 5.7.509`: the NUS From
domain failed DMARC with a reject policy. A separate user-authorized direct SES
test used an already-verified Gmail sender. The user then explicitly requested
that all demo application notifications use that Gmail address. This is a demo
sender selection, not a claim of domain-authenticated sending or inbox delivery.

Changed only ignored operator `ses_sender` and the explicit verified recipient
identity list in the existing `infra/envs/demo` checkout. Adopted the existing
verified Gmail identity into `module.platform.aws_ses_email_identity.sender`
using a state backup, detach and import, rather than deleting the school identity
or requesting sender verification again. The school identity remains intact;
only the selected Gmail identity is now tracked at the sender resource address.

The reviewed plan contained four in-place updates: notification intake and
dispatch sender environments, the dispatch SES inline policy, and the existing
CloudFront normalization. No additions, deletions, image rebuilds, database,
queue replay or capacity changes. Terraform apply succeeded. Both notification
Lambdas are Active/Successful with the selected sender; recipient grants restrict
the From address to that sender. All existing notification templates share this
configuration. Runtime verification uses an empty intake batch and does not send
messages. Operator configuration/evidence remains ignored under
`.local/gmail-sender-*`; retain the selected `ses_sender` and recipient list on
subsequent demo applies. The Gmail/school test recipient identities remain subject
to SES sandbox verification.
