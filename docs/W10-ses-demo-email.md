# W10 SES demo email

Issue #386 / PR #387. The user confirmed the deployed email flow works on
6 November 2026 after selecting the verified Gmail identity as the demo sender.
All application notification templates share that configured sender. PR #387
merged on 6 November 2026 (ce2031f); issue #386 is closed and W10 is complete.
This demo configuration does not establish domain-authenticated production sending.

## Terraform configuration

Use the existing operator checkout `.local/aws-current`, root `infra/envs/demo`
and shared `demo/terraform.tfstate` backend. Preserve its ignored
`terraform.tfvars`, `images.tfvars.json` and backend configuration. The current
operator `ses_sender` is `lohnorbert@gmail.com`; it is deliberately not a shared
module default. New deployments must select and verify their own sender.

Set `ses_recipient_identity_arns` to the exact regional identity ARNs of the
verified demo recipients. The current operator list includes the user's Gmail
and approved school test mailbox. SES remains in sandbox mode: adding an ARN
does not verify a recipient or remove the provider's verification requirement.
The default list is empty; wildcard and foreign-account/region identities are
rejected. Only notification dispatch receives the additional `SendEmail` and
`SendRawEmail` permissions, constrained by `ses:FromAddress` to the configured
sender mailbox. Existing sender permissions are preserved.

The already-verified Gmail identity was imported into
`module.platform.aws_ses_email_identity.sender` after backing up state and
removing the prior sender from that resource address. The school identity was
not deleted. Do not recreate or reverify the imported identity, or apply old
operator sender settings without reviewing the identity and IAM plan.

The sender rollout changed two notification Lambda environments, the dispatch
SES policy and the pre-existing CloudFront optional-field normalization only
(0 additions, 4 in-place updates, 0 destruction). Images, capacity, database
schemas and event routes were unchanged. Both Lambdas are Active/Successful;
the effective sender and secret-override checks passed. The final plan has no
SES/application changes, only the existing CloudFront normalization.

## Delivery evidence and limitations

The original school sender produced the explicit remote rejection
`550 5.7.509`: the NUS From domain failed DMARC with a reject policy. SES mailbox
verification alone did not provide aligned domain authentication. A separate
direct SES Gmail-sender test was authorized before the user selected that sender
for the app. The user subsequently confirmed the deployed email flow works.
Gmail sender selection is a demo workaround; it does not give the team DNS
control over gmail.com or establish aligned sender-domain authentication.

Before correcting sender configuration, the dispatch role also returned
`AccessDenied` for a verified recipient identity. Its original sender-only
policy omitted that runtime resource. The scoped recipient grant fixes that
permission failure. Sender-only IAM simulation had not detected it; subsequent
checks included the recipient resource and From-address condition.

SES acceptance and inbox delivery are separate outcomes. Notification status
`sent` records SES acceptance and a provider message ID. On separate explicit
user authorization, exactly the latest definitively rejected consultation
receipt was requeued after checking its ready PDF, payment and patient/tenant
ownership. Scheduled dispatch accepted its attachment at 00:36:33 SGT on
6 November, with attempts 2 and no error. Other failed jobs were unchanged.
No messages were sent or replayed during the later sender configuration rollout.
Never reset `uncertain` jobs without resolving possible duplicate delivery.

SES bounce forwarding remains enabled to the sending mailbox. Virtual
Deliverability Manager is not enabled; message insights were unavailable and
no paid delivery feature was enabled. For authenticated production sending,
use a domain controlled by the team and configure DKIM/MAIL FROM alignment.
See [AWS DMARC guidance](https://docs.aws.amazon.com/ses/latest/dg/send-email-authentication-dmarc.html).

## Verification and operator evidence

Focused background-jobs tests cover recipient permissions, sender restriction,
non-dispatch role isolation, wildcard rejection and foreign-identity rejection.
Deployed verification checked both Lambda configurations, absence of conflicting
secret sender overrides, scoped IAM permissions, and an empty intake invocation
that sends no email. IAM simulation permits both SES APIs from the selected
sender to the verified school recipient.

Account-specific plans, image pins, state backups and email/message identifiers
remain ignored under `.local/`. Relevant evidence includes `gmail-sender-*`,
`w10-*`, `email-role-diagnostic/`, `receipt-retry-*` and
`email-diagnostic-result.json`. Never commit operator secrets, state or plans.

Final pre-merge verification on 6 November 2026: all eight Terraform roots/modules
validate, recursive formatting and diff checks pass, all 23 mocked Terraform
runs pass (background-jobs 6, demo-platform 14, public-edge 3), all three edge
routing tests pass and all ten TURN helper tests pass. GitHub Actions jobs were
not started because the GitHub account is locked for billing; their red statuses
are not test execution failures. The user confirmed that the deployed email
flow works and authorized merging the related changes.
