/** Run the existing local adapter probes with Vite's installed TypeScript runtime. */
import { createRequire } from 'node:module'
import { fileURLToPath, pathToFileURL } from 'node:url'
import path from 'node:path'

const root = fileURLToPath(new URL('..', import.meta.url))
const probes = new Set([
  'check_records_frontend.mts',
  'check_scheduling_frontend.mts',
])
const probe = process.argv[2]
if (!probes.has(probe)) {
  console.error(
    `Usage: node dev/run_frontend_probe.mjs ${[...probes].join(' | ')}`,
  )
  process.exitCode = 1
} else {
  const require = createRequire(path.join(root, 'apps/web/package.json'))
  const { createServer } = await import(
    pathToFileURL(require.resolve('vite')).href
  )
  const server = await createServer({
    root: path.join(root, 'apps/web'),
    configFile: path.join(root, 'apps/web/vite.config.ts'),
    server: { middlewareMode: true, hmr: false, watch: null },
    appType: 'custom',
    logLevel: 'error',
  })
  try {
    if (server.config.env.VITE_USE_AWS === 'true')
      throw new Error('Frontend probes require local API configuration.')
    await server.ssrLoadModule(path.join(root, 'dev', probe))
  } finally {
    await server.close()
  }
}
