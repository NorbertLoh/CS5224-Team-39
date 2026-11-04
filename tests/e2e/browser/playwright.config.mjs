import { defineConfig } from 'playwright/test';
import { settings } from './settings.mjs';

const config = settings();
export default defineConfig({
  testDir: './specs',
  timeout: 90_000,
  globalTimeout: 25 * 60_000,
  expect: { timeout: 20_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  forbidOnly: true,
  outputDir: './test-results',
  reporter: [
    ['list'], ['html', { open: 'never' }],
    ['json', { outputFile: './test-results/results.json' }],
    ['junit', { outputFile: './test-results/junit.xml' }],
  ],
  metadata: { target: config.target, baseURL: config.baseURL, scope: 'Selected project only; not full AWS acceptance' },
  use: {
    baseURL: config.baseURL,
    browserName: 'chromium',
    ignoreHTTPSErrors: config.ignoreHTTPSErrors,
    actionTimeout: 20_000,
    navigationTimeout: 30_000,
    screenshot: 'only-on-failure',
    // Traces include network credentials. Enable only in a private local run.
    trace: 'off',
    video: 'off',
  },
  projects: [
    { name: 'smoke', testMatch: 'smoke.spec.mjs' },
    { name: 'booking', testMatch: 'booking.spec.mjs' },
    { name: 'stripe', testMatch: 'stripe.spec.mjs' },
    { name: 'evidence', testMatch: 'evidence.spec.mjs' },
  ],
});
