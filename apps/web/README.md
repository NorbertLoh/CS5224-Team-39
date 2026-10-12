# Web frontend

React + TypeScript + Vite frontend. Use Node 22.12+ or Node 24+ and npm.

From `apps/web`:

```sh
npm ci
npm run dev
npm run build
npm test
npm run preview
```

Development runs at http://127.0.0.1:5173. Preview serves the built `dist/` at http://127.0.0.1:4173. `npm run typecheck` checks TypeScript separately. The lockfile is committed; use `npm ci` for reproducible installs.

`dist/` contains static assets suitable for S3/CloudFront; the Vite development/preview servers are local tools, not production hosting. Configure cloud routing in W04. Browser-visible `VITE_*` environment variables are substituted at build time, so never put credentials or secrets in them.

F08 provides the query provider, typed API transport and shared loading/error states. F07 adds route modules/layouts. This scaffold has no authentication or live business API integration yet. Planned feature groups: storefront, patient, doctor, clinic administration and platform administration.

## API configuration and feature queries

Copy `.env.example` to `.env` if needed. `VITE_API_BASE_URL` defaults to `/api/v1`.
For a separate trusted API origin, set it to an absolute HTTP(S) URL ending in
`/api/v1`, such as `https://api.example.test/api/v1`. Restart Vite or rebuild after
changing it. No Vite proxy is installed here: same-origin `/api/v1` forwarding
belongs to F10/W04. Without that proxy or a configured running API, requests
cannot reach a business service. Cross-origin APIs require an explicit CORS
allowlist and exposed `X-Request-ID`/`Retry-After` headers.

`src/lib/api-types.ts` implements [C01 wire shapes](../../contracts/api-conventions.md).
`api.get<T>()` expects a JSON response; `api.request<T>()` supports JSON writes
and returns `T | undefined` (204 returns undefined). Both accept service-relative
paths, separate query parameters and an `AbortSignal`. Dynamic IDs must be
URL-encoded. Query values are encoded automatically; null/undefined values are
omitted. Arbitrary origins and traversal in request paths are rejected. Binary
downloads and external signed URLs should use a separate feature-specific fetch,
without adding this API client's bearer token.

`ApiError` carries kind, HTTP status, code, requestId, field details and optional
Retry-After delay. C01 envelopes are checked before use; unstructured server/proxy
errors get safe messages. Network failures get a connection message; cancellation
remains AbortError. Type parameters describe the agreed response but do not
validate successful payloads at runtime. Feature-specific decoders may validate
their domain payloads when needed.

The root `QueryClientProvider` owns one in-memory client. GET queries can retry
twice for network failures or 429/500/502/503/504; auth, validation, malformed
responses and mutations do not retry. Retry-After is honored up to 30 seconds;
longer waits disable automatic retries. Queries are fresh for 30 seconds, unused
entries are collected after five minutes, and window focus does not refetch.
Use queries for safe reads and mutations for writes; override freshness in a
feature only when its workflow requires it. The API transport itself never retries.

Use a resolved user/clinic/role scope in query keys, include every filter and
cursor, and pass TanStack's signal through. This example shows the C01 synthetic
appointment shape; implement the actual endpoint in the owning C02/S04 tasks:

```tsx
import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { apiQueryKey, type QueryScope } from '@/lib/query-client'
import type { CursorPage, ResourceId, UtcTimestamp } from '@/lib/api-types'
import { LoadingState } from '@/components/LoadingState'
import { ErrorState } from '@/components/ErrorState'

type Appointment = { appointment_id: ResourceId; starts_at: UtcTimestamp }

export function Appointments({ scope }: { scope: QueryScope }) {
  const query = useQuery({
    queryKey: apiQueryKey(scope, 'scheduling', 'appointments', { limit: 25 }),
    queryFn: ({ signal }) => api.get<CursorPage<Appointment>>(
      '/scheduling/appointments', { query: { limit: 25 }, signal },
    ),
  })
  if (query.isPending) return <LoadingState message="Loading appointments…" />
  if (query.isError) return <ErrorState error={query.error} onRetry={() => { void query.refetch() }} retrying={query.isFetching} />
  return <p>{query.data.items.length} appointments</p>
}
```

On filter or clinic changes, reset pagination. Keys separate cached scopes but
do not authorize access; services validate membership. A01/A02 should create an
authenticated client with `createApiClient({ baseUrl, getAccessToken })`, where
the callback returns the current access token on each request. The exported
`api` is currently anonymous; F08 neither stores tokens nor refreshes them.
Never put tokens in query keys. When identity/permissions change or the user logs
out, stop rendering the old authenticated subtree, await
`queryClient.cancelQueries()`, then call `queryClient.clear()` before mounting
the new scope. Do not persist clinical caches to browser storage. Avoid pending
mutations writing data into a new session's cache; authentication tasks must
coordinate the session transition and mutation completion.

`LoadingState` announces progress and respects reduced motion. `ErrorState`
accepts an unknown error, renders safe API messages and correlation references,
hides cancellation, and offers an optional retry button with a disabled running
state. It does not display arbitrary exception text or field values.

`npm test` runs focused transport, retry/cache and server-rendered component
checks with synthetic responses, without a live API. `npm run build` includes
the frontend typecheck. These checks do not establish live service integration.
Patterns follow [TanStack's provider/query guide](https://tanstack.com/query/latest/docs/framework/react/quick-start)
and [cancellation guide](https://tanstack.com/query/latest/docs/framework/react/guides/query-cancellation).

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
