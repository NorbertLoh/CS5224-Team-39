import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './tests/browser',
  timeout: 45000,
  workers: 1,
  reporter: [['list'], ['json', { outputFile: 'test-results/report.json' }]],
  use: {
    baseURL: 'http://127.0.0.1:9000',
    launchOptions: { args: ['--use-fake-device-for-media-stream', '--use-fake-ui-for-media-stream'] },
  },
  webServer: [
    { command: 'node server.mjs', url: 'http://127.0.0.1:9000/healthz',
      env: { SPIKE_HOST: '127.0.0.1', SPIKE_PORT: '9000', SPIKE_TLS_CERT: '', SPIKE_TLS_KEY: '' } },
    { command: 'node admission-server.mjs', url: 'http://127.0.0.1:9002/healthz',
      env: { X02_PORT: '9002', X02_TTL_SECONDS: '60' } },
  ],
});
