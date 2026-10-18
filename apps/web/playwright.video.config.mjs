import { defineConfig } from '@playwright/test';
export default defineConfig({
  testDir: './tests/browser', testMatch: '*.spec.mjs', timeout: 45000, workers: 1,
  reporter: 'list', use: { ignoreHTTPSErrors: true,
    launchOptions: { args: ['--use-fake-device-for-media-stream', '--use-fake-ui-for-media-stream'] } },
  webServer: [
    { command: 'node tests/browser/server.mjs', url: 'http://127.0.0.1:9051/healthz' },
    { command: 'npm run dev -- --host 0.0.0.0 --port 5174', url: 'http://127.0.0.1:5174' },
  ],
});
