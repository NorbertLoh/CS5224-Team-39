# RF03: sign-in page

Open `/sign-in`, or choose **Sign in** from the signed-out application header.
The page uses a forest-green introduction panel, a clear sign-in action and a
compact mobile layout. It includes keyboard focus indicators and a skip link.
Signed-in visitors can return home to select their existing workspace.

**Continue to sign in** starts the existing hosted authorization-code + PKCE
flow. Credentials are entered on the provider's page. Configuration errors
disable the action, pending requests disable repeat clicks, and failures show
retry feedback. Callback, refresh, logout and role authorization retain their
existing behavior.

## Setup

No new dependencies, environment variables, migrations or backend changes.
Use the existing `apps/web/.env` Cognito configuration and registered callback
origin documented in [the local journey](I02-local-journey.md). Run
`npm run dev` from `apps/web`. A different development port must be registered
with the authentication provider before completing an actual login.

The local review client also has callback URLs
`http://127.0.0.1:5174/auth/callback` and `http://localhost:5174/auth/callback`,
with matching logout URLs at each origin's `/`. These local registrations
preserve the existing 8443/5173 URLs. Rerunning the standard Cognito bootstrap
replaces the allowlist, so register the preview URLs again if that setup is reset.

## Verification

Verified locally on 23 October 2026:

- Frontend lint, TypeScript and production build.
- All 138 existing frontend tests, including session and navigation/access tests.
- Chromium layouts at 320, 390, 768 and 1440 pixels; no horizontal overflow.
- Keyboard skip-link navigation and header-to-sign-in navigation.
- A simulated handoff failure displays feedback and re-enables the action.
- Authorization handoff includes state, an S256 challenge and the correct
  callback origin. The destination was intercepted for inspection; this check
  does not claim a completed live provider login or AWS validation.
- After registering the preview origin, the real local authorization redirect
  successfully opened the Floci username/password sign-in form.
- Signed-in state exposes workspace navigation without another sign-in action.
- No browser page errors during these checks.

Screenshots use synthetic page content. Journey cards are decorative illustrations,
not patient records or live appointment status.

## Desktop

![Desktop sign-in page](images/RF03-sign-in-desktop.png)

## Mobile

![Mobile sign-in page](images/RF03-sign-in-mobile.png)
