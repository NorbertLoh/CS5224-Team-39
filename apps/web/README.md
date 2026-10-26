# Web frontend

Account creation is available from **Create an account** on `/sign-in`, with email
verification and automatic patient provisioning on first sign-in. See
[RF13 setup and verification](../../docs/RF13-account-signup.md), including local
Floci email capture and the required Cognito hosted-login self-service scope.

React + TypeScript + Vite frontend. Use Node 22.12+ or Node 24+ and npm.

From `apps/web`:

```sh
npm ci
npm run lint
npm run dev
npm run build
```

Development runs at http://127.0.0.1:5173. `npm run typecheck` checks TypeScript separately. The lockfile is committed; use `npm ci` for reproducible installs.

`dist/` contains static assets suitable for S3/CloudFront; the Vite development server is a local tool, not production hosting. Configure cloud routing in W04. Browser-visible `VITE_*` environment variables are substituted at build time, so never put credentials or secrets in them.

The clinic list, public storefront at `/clinics/<slug>` and profile editor at
`/clinic-admin/clinics/<tenant UUID>/profile` always use real identity/tenant APIs.
Profile fields persist in PostgreSQL; logo files persist in S3. There are no
runtime fixtures, browser-only saves or fallback data. Booking, checkout, records, documents and medication orders also use their real service APIs.

Staff management at `/clinic-admin/clinics/<tenant UUID>/staff` uses the real
identity GET/PUT/DELETE membership APIs with the same local/AWS configuration.
Open **Manage staff** from the clinic list or profile editor. Clinic administrators
and platform administrators can assign existing subjects, replace doctor/admin
roles, revoke access and reactivate memberships. The backend protects the last
active administrator. Staff are shown by identity subject UUID because the
membership API does not expose names or account search. This page does not create
accounts; provision subjects first using the existing backend setup.

`VITE_USE_AWS=false` selects local API/Cognito configuration; `true` selects
`VITE_AWS_API_BASE_URL` and `VITE_AWS_COGNITO_*`. Missing AWS values show errors.
Copy `.env.example` and restart Vite (or rebuild) after changing settings.
See [complete local backend setup and AWS configuration](../../docs/clinic-backend.md).

## Calling an API

`apiFetch()` is a small wrapper around `fetch()`. It adds the API base URL,
optionally attaches an access token, and throws when the HTTP response fails.
It returns the normal `Response`; feature pages parse their own data:

```ts
import { apiFetch } from '@/lib/api'
import type { CursorPage } from '@/lib/api-types'

type Appointment = { appointment_id: string; starts_at: string }
const response = await apiFetch('/scheduling/appointments?limit=25', {
  signal, // optional AbortSignal, including the signal from useQuery
  accessToken, // optional current access token from authentication
})
const appointments: CursorPage<Appointment> = await response.json()
```

Feature APIs live in their owning feature folders.
Pass ordinary fetch options for writes (`method`, JSON.stringify(body), and a
Content-Type header). Skip response.json() for a 204 response. Construct query
strings with URLSearchParams and encode dynamic IDs with encodeURIComponent.
Response types describe [C01 wire shapes](../../contracts/api-conventions.md);
feature pages handle domain validation and field errors when needed.

The local API base defaults to `/api/v1`. Vite forwards identity, tenant and
template prefixes to ports 8001, 8002 and 8000, stripping the service prefix.
Server-only `IDENTITY_API_TARGET`, `TENANT_API_TARGET` and `TEMPLATE_API_TARGET`
can override those addresses. The static
production build needs deployed gateway routing and explicit CORS for a separate
origin. Never attach API tokens to external signed download URLs.

The root query provider is available for feature pages that use `useQuery`.
Automatic retries are off. Use keys such as
`['appointments', subject, tenantId, role, filters]`, including the current scope
and every filter/cursor. On logout or identity changes, stop rendering the old
scope, await queryClient.cancelQueries(), and call queryClient.clear().
Keep clinical caches in memory; services still enforce access.

`LoadingState` announces progress. `ErrorState` accepts a safe display message
and an optional retry callback. Do not display raw exception/server text.
Native fetch cancellation is preserved; callers should ignore AbortError.
`npm run build` includes typechecking. Frontend fixture screens, unit/browser test
harnesses and the local Vite preview command were removed in RF04. Verify live
journeys using the service setup and walkthroughs in `docs/`; lint and build do
not establish live integration.

## Frontend checks in CI

`npm run lint` checks JavaScript, TypeScript and TSX with ESLint's recommended
JavaScript/TypeScript rules. Generated `dist/` and `node_modules/` are ignored.
GitHub Actions runs separate ESLint and typecheck/build jobs on pushes and pull
requests using Node 24 and `npm ci`. Errors or warnings fail the lint check.
The build job runs `npm run build`, which first runs `tsc --noEmit` and then Vite's
production build; either failure fails the job. Run `npm run lint` and
`npm run build` locally to reproduce the frontend checks. These checks require
no backend, database or Floci instance. Backend Ruff checks are documented in
the [service template](../../services/template/README.md).
TypeScript uses 6.0.x to match the ESLint parser's supported compiler versions.
Configuration follows the [typescript-eslint quickstart](https://typescript-eslint.io/getting-started/).

## UI components and styling

Use Tailwind CSS v4 utilities for layout and shadcn/ui components for shared controls. Tailwind runs through the Vite plugin; `src/index.css` contains the generated theme tokens and base styles. Avoid a second handwritten component stylesheet.

The shadcn Nova/Radix setup is configured in `components.json`. Generated components are committed under `src/components/ui`, and `src/lib/utils.ts` provides `cn()` for class merging. Import them with the `@/` alias:

```tsx
import { Button } from '@/components/ui/button'
```

Add only components your feature needs, from `apps/web`:

```sh
npx shadcn@latest add input dialog
```

Commit generated component files and dependency/lockfile changes together. Keep feature-specific layouts in their feature folder; coordinate edits to shared components and theme tokens with teammates. Do not rerun `init` or overwrite shared component customisations without checking the diff.

Setup references: [shadcn Vite guide](https://ui.shadcn.com/docs/installation/vite), [Tailwind Vite guide](https://tailwindcss.com/docs/installation/using-vite), [Vite guide](https://vite.dev/guide/).
