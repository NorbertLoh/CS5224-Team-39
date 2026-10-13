import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { fileURLToPath } from 'node:url'

export default defineConfig(({ mode }) => ({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) } },
  server: {
    strictPort: true,
    proxy: {
      '^/api/v1/tenant(?:/|\\?|$)': {
        target: loadEnv(mode, process.cwd(), 'TENANT_').TENANT_API_TARGET || 'http://127.0.0.1:8002',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api\/v1\/tenant(?=\/|\?|$)/, '') || '/',
      },
      '^/api/v1/template(?:/|\\?|$)': {
        target: loadEnv(mode, process.cwd(), 'TEMPLATE_').TEMPLATE_API_TARGET || 'http://127.0.0.1:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api\/v1\/template(?=\/|\?|$)/, '') || '/',
      },
    },
  },
  preview: { strictPort: true },
}))
