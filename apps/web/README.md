# Web frontend

React + TypeScript + Vite frontend. Use Node 22.12+ or Node 24+ and npm.

From `apps/web`:

```sh
npm ci
npm run dev
npm run build
npm run preview
```

Development runs at http://127.0.0.1:5173. Preview serves the built `dist/` at http://127.0.0.1:4173. `npm run typecheck` checks TypeScript separately. The lockfile is committed; use `npm ci` for reproducible installs.

`dist/` contains static assets suitable for S3/CloudFront; the Vite development/preview servers are local tools, not production hosting. Configure cloud routing in W04. Browser-visible `VITE_*` environment variables are substituted at build time, so never put credentials or secrets in them.

Role layouts and feature routes are available. F08 adds the API client and shared UI; A01/A02/U05 add authentication, access control and tenant selection. All portal paths are currently public prototype previews. A route or navigation label does not enforce authorization; backend services must enforce access independently.

| Path | Area |
| --- | --- |
| `/` | Portal selection |
| `/clinics/:clinicSlug` | Storefront placeholder; slug is display-only until tenant lookup is implemented |
| `/patient` | Patient portal |
| `/doctor` | Doctor portal |
| `/clinic-admin` | Clinic dashboard |
| `/platform-admin` | Platform administration |

Registered pages are placeholders, with no real records, payments or booking flows. Unknown routes show a fallback page; nested unknown routes retain their portal layout.

## Adding a feature page

1. Work inside `src/features/<feature>/`. Replace its placeholder with your page component in that feature's `routes.tsx` registration.
2. Each registration is a typed `FeatureRegistration`. Its `pages` keys are portal roles; page paths are relative to that portal, such as `appointments`. Keep each path unique within a role.
3. For a new feature, add its export to `src/features/registry.ts` once. That registry generates both child routes and navigation. Coordinate this shared file with other teammates.
4. Detail routes such as `appointments/:appointmentId` must set `navigation: false`; link to them from the list page with a concrete ID. Avoid absolute paths in feature registrations.

The shell and router live under `src/app/`; page contributors normally do not need to edit them. `NavLink` marks the current section. Storefront routes stay outside the role layouts.

Smoke check: open every portal, follow its navigation, refresh a nested URL (for example `/doctor/availability`), and open an unknown route. At mobile width the navigation should stack above the content.

The browser router requires the hosting layer to serve `index.html` for UI deep links. W04 must implement this for CloudFront/S3, preserving real errors for API requests and missing assets. Local Vite development and preview already support UI fallback.

Build tool requirements: [Vite guide](https://vite.dev/guide/). Routing pattern: [React Router data routing](https://reactrouter.com/start/data/routing).
