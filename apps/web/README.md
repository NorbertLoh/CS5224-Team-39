# Web frontend

React + TypeScript + Vite frontend. Use Node 22.12+ or Node 24+ and npm.

From `apps/web`:

```sh
npm ci
npm run lint
npm run dev
npm run build
npm run preview
```

Development runs at http://127.0.0.1:5173. Preview serves the built `dist/` at http://127.0.0.1:4173. `npm run typecheck` checks TypeScript separately. The lockfile is committed; use `npm ci` for reproducible installs.

`dist/` contains static assets suitable for S3/CloudFront; the Vite development/preview servers are local tools, not production hosting. Configure cloud routing in W04. Browser-visible `VITE_*` environment variables are substituted at build time, so never put credentials or secrets in them.

F07 adds route modules/layouts; F08 adds the API client and shared UI. This scaffold has no authentication or API integration yet. Planned feature groups: storefront, patient, doctor, clinic administration and platform administration.

## Frontend lint in CI

`npm run lint` checks JavaScript, TypeScript and TSX with ESLint's recommended
JavaScript/TypeScript rules. Generated `dist/` and `node_modules/` are ignored.
GitHub Actions runs the same command on pushes and pull requests using Node 24
and `npm ci`. Errors or warnings fail the check. This frontend lint increment
does not complete F15's planned build/type and backend lint checks.
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
