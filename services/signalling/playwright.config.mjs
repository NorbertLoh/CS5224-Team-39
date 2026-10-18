import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './tests/browser', timeout: 45000, workers: 1, reporter: 'list',
  use: { ignoreHTTPSErrors: true, launchOptions: {
    args: ['--use-fake-device-for-media-stream', '--use-fake-ui-for-media-stream'],
  } },
  webServer: { command: 'node tests/fixture-server.mjs', url: 'http://127.0.0.1:9050/healthz' },
});
