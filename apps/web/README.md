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

F07 adds route modules/layouts; F08 adds the API client and shared UI. This scaffold has no authentication or API integration yet. Planned feature groups: storefront, patient, doctor, clinic administration and platform administration.

Build tool requirements: [Vite guide](https://vite.dev/guide/).
