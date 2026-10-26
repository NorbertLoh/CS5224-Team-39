# RF13 account signup

The user deferred other sign-in options: the page offers email/password sign-in
and Create an account, with no hosted-login button. Error guidance no longer
points to that removed option. The existing OAuth callback/session support remains
available for future provider integration; accounts needing additional verification
receive an explicit message that the step is not available on this page yet.

At `/sign-in`, choose **Create an account**. The form collects full name, email,
password and password confirmation, then calls Cognito `SignUp`. Unconfirmed users
enter their emailed code (`ConfirmSignUp`); **Resend verification code** uses
`ResendConfirmationCode`, with a 60-second UI cooldown. **I have a verification
code** resumes confirmation after leaving or reloading the page. Passwords stay
in component memory and are cleared after successful account creation.

After confirmation, sign in normally. Only when identity `/me` returns
`identity_not_provisioned`, the frontend calls authenticated
`POST /api/v1/identity/me/registration`. The service verifies the access token,
loads attributes through Cognito `GetUser`, requires the matching `sub` and
`email_verified=true`, and creates a patient identity from those trusted
attributes. Existing identities and memberships are returned unchanged. Database
uniqueness makes retries safe; email collisions never attach a different Cognito
subject to an existing identity. Client-supplied roles, subjects and names are
not used by this endpoint. No migration is required. Patient contact/delivery
details remain in the existing Profile page.

## Configuration

The existing `VITE_COGNITO_*` / `VITE_AWS_COGNITO_*` settings apply; no new frontend
variables. Identity uses `SERVICE_AUTH_ISSUER` for the AWS Cognito API origin, or
the existing `SERVICE_AWS_ENDPOINT_URL` in local/test. Configure public SPA client
attributes to permit `email` and `name`, enable self-registration, and automatically
verify email. Configure the sender and email delivery on AWS. Keep the current
password-token policy and signature/issuer/client/scope validation enabled.

Hosted PKCE now requests `aws.cognito.signin.user.admin` alongside `openid email
profile` so `GetUser` can read the signed-in user's attributes during first-login
provisioning. Add that reserved scope to the Cognito app client's allowed OAuth
scopes before using this build. It permits Cognito self-service operations and
does not grant TeleLink administrator roles. Password login already issues it.

`dev/floci/cognito.sh` enables signup/email verification for new and existing
**synthetic local** pools and adds the reserved scope to the local app client.
Rerun the offline bootstrap as documented in local development. This bootstrap
sets local pool defaults; do not use it against a customised or AWS pool. For an
existing customised pool, preserve all current pool settings when enabling signup.
Rebuild/recreate only web and identity for the new application code.

Floci 2.2.0 captures confirmation emails at
`http://localhost:4566/_aws/ses` instead of delivering them to a real inbox. Find
the message for your synthetic signup address and enter its code in the app.
Treat captured messages as private local development data. No fixed code or
verification bypass is used in the application.

The API flow follows the AWS references for
[SignUp](https://docs.aws.amazon.com/cognito-user-identity-pools/latest/APIReference/API_SignUp.html),
[ConfirmSignUp](https://docs.aws.amazon.com/cognito-user-identity-pools/latest/APIReference/API_ConfirmSignUp.html),
and [ResendConfirmationCode](https://docs.aws.amazon.com/cognito-user-identity-pools/latest/APIReference/API_ResendConfirmationCode.html).

## Verification

- All 150 identity tests pass against a separate disposable RF13 PostgreSQL
  database, including authentication, verified matching Cognito attributes,
  fail-closed provider errors, patient-only roles, idempotence, unchanged existing
  identities, and email-takeover rejection.
- Frontend lint, TypeScript and production build pass; existing bundle-size
  advisory remains.
- Actual local browser signup, captured-email confirmation and first password
  login reached `/patient` and loaded the empty appointments list. Password
  mismatch and incorrect confirmation code showed readable errors. Local
  `ResendConfirmationCode` generated another captured email.
- Desktop and 390px mobile-width layouts were visually checked. Switching forms
  focuses the heading so the new form is visible and keyboard navigation resumes
  in the correct place.
- Actual AWS email delivery, hosted first-login provisioning and AWS deployment
  remain unverified.

Issue #284 stays In progress until PR #285 is merged and completion criteria are met.
