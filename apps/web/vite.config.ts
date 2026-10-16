import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { fileURLToPath } from 'node:url'

function blockInternal(request: { url?: string }) {
  try {
    const path = decodeURIComponent((request.url ?? '').split('?')[0])
    return /^\/api\/v1\/(?:clinical-records|fulfilment|identity|tenant)\/internal(?:\/|$)/.test(
      path,
    )
      ? false
      : undefined
  } catch {
    return false
  }
}

export default defineConfig(({ mode }) => ({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) } },
  server: {
    strictPort: true,
    proxy: {
      '^/api/v1/clinical-records(?:/|\\?|$)': {
        target:
          loadEnv(mode, process.cwd(), 'RECORDS_').RECORDS_API_TARGET ||
          'http://127.0.0.1:8005',
        changeOrigin: true,
        bypass: blockInternal,
      },
      '^/api/v1/fulfilment(?:/|\\?|$)': {
        target:
          loadEnv(mode, process.cwd(), 'FULFILMENT_').FULFILMENT_API_TARGET ||
          'http://127.0.0.1:8006',
        changeOrigin: true,
        bypass: blockInternal,
        rewrite: (path) =>
          path.replace(/^\/api\/v1\/fulfilment(?=\/|\?|$)/, '') || '/',
      },
      '^/api/v1/scheduling(?:/|\\?|$)': {
        target:
          loadEnv(mode, process.cwd(), 'SCHEDULING_').SCHEDULING_API_TARGET ||
          'http://127.0.0.1:8003',
        changeOrigin: true,
        bypass: (request) =>
          /^\/api\/v1\/scheduling\/internal(?:\/|\?|$)/.test(request.url ?? '')
            ? false
            : undefined,
        rewrite: (path) =>
          path.replace(/^\/api\/v1\/scheduling(?=\/|\?|$)/, '') || '/',
      },
      '^/api/v1/identity(?:/|\\?|$)': {
        bypass: blockInternal,
        target:
          loadEnv(mode, process.cwd(), 'IDENTITY_').IDENTITY_API_TARGET ||
          'http://127.0.0.1:8001',
        changeOrigin: true,
        rewrite: (path) =>
          path.replace(/^\/api\/v1\/identity(?=\/|\?|$)/, '') || '/',
      },
      '^/api/v1/tenant(?:/|\\?|$)': {
        bypass: blockInternal,
        target:
          loadEnv(mode, process.cwd(), 'TENANT_').TENANT_API_TARGET ||
          'http://127.0.0.1:8002',
        changeOrigin: true,
        rewrite: (path) =>
          path.replace(/^\/api\/v1\/tenant(?=\/|\?|$)/, '') || '/',
      },
      '^/api/v1/template(?:/|\\?|$)': {
        target:
          loadEnv(mode, process.cwd(), 'TEMPLATE_').TEMPLATE_API_TARGET ||
          'http://127.0.0.1:8000',
        changeOrigin: true,
        rewrite: (path) =>
          path.replace(/^\/api\/v1\/template(?=\/|\?|$)/, '') || '/',
      },
    },
  },
  preview: { strictPort: true },
}))
