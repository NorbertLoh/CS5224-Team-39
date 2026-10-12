# Web frontend

React + TypeScript + Vite frontend. Use Node 22.12+ or Node 24+ and npm.

From `apps/web`:

```sh
npm ci
npm run lint
npm run dev
npm run build
npm test
npm run preview
```

Development runs at http://127.0.0.1:5173. Preview serves the built `dist/` at http://127.0.0.1:4173. `npm run typecheck` checks TypeScript separately. The lockfile is committed; use `npm ci` for reproducible installs.

`dist/` contains static assets suitable for S3/CloudFront; the Vite development/preview servers are local tools, not production hosting. Configure cloud routing in W04. Browser-visible `VITE_*` environment variables are substituted at build time, so never put credentials or secrets in them.

F08 provides the query provider, a small fetch helper and shared loading/error states. F07 adds route modules/layouts. This scaffold has no authentication or live business API integration yet. Planned feature groups: storefront, patient, doctor, clinic administration and platform administration.

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

This illustrates a future endpoint; domain APIs remain their owning tasks.
Pass ordinary fetch options for writes (`method`, JSON.stringify(body), and a
Content-Type header). Skip response.json() for a 204 response. Construct query
strings with URLSearchParams and encode dynamic IDs with encodeURIComponent.
Response types describe [C01 wire shapes](../../contracts/api-conventions.md);
feature pages handle domain validation and field errors when needed.

Copy `.env.example` to `.env` if needed. `VITE_API_BASE_URL` defaults to `/api/v1`;
for a separate trusted origin use a URL ending in `/api/v1`. Restart Vite or
rebuild after changes. Vite forwards `/api/v1/template` to the Compose API at
`http://127.0.0.1:8000`, stripping the prefix. If its host port changes, set
`TEMPLATE_API_TARGET` in this app's `.env` and restart Vite. This server-only
setting is not bundled into the frontend. See [local startup](../../docs/local-development.md).
Dev and preview support this forwarding; production routing belongs to W04.
Other service prefixes are not wired yet; cross-origin servers need CORS
configuration. Authentication/token refresh belongs to A01/A02.
Never attach API tokens to external signed download URLs.

The root query provider is available for feature pages that use `useQuery`.
Automatic retries are off. Use keys such as
`['appointments', subject, tenantId, role, filters]`, including the current scope
and every filter/cursor. On logout or identity changes, stop rendering the old
scope, await queryClient.cancelQueries(), and call queryClient.clear().
Keep clinical caches in memory; services still enforce access.

`LoadingState` announces progress. `ErrorState` accepts a safe display message
and an optional retry callback. Do not display raw exception/server text.
Native fetch cancellation is preserved; callers should ignore AbortError.
`npm test` checks the helper and components; `npm run build` includes typechecking.
These synthetic checks do not establish live API integration.

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
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
```

Add only components your feature needs, from `apps/web`:

```sh
npx shadcn@latest add input dialog
```

Commit generated component files and dependency/lockfile changes together. Keep feature-specific layouts in their feature folder; coordinate edits to shared components and theme tokens with teammates. Do not rerun `init` or overwrite shared component customisations without checking the diff.

Setup references: [shadcn Vite guide](https://ui.shadcn.com/docs/installation/vite), [Tailwind Vite guide](https://tailwindcss.com/docs/installation/using-vite), [Vite guide](https://vite.dev/guide/).
