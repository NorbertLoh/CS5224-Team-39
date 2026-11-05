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
