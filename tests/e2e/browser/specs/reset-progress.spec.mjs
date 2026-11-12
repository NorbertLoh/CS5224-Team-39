// Reset HTTP calls are fully intercepted: these tests never submit a real job.
import { test, expect } from 'playwright/test';

async function mockPage(page, reset) {
  await page.addInitScript(() => {
    localStorage.setItem('telelink.session', JSON.stringify({
      accessToken: 'mock-reset-session', refreshToken: 'mock-refresh',
      expiresAt: Date.now() + 3600000,
    }));
  });
  await page.route('**/api/v1/**', async route => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith('/identity/demo-reset')) return reset(route);
    if (route.request().method() !== 'GET') return route.abort();
    if (path.endsWith('/identity/me')) return route.fulfill({ json: {
      subject_id: '00000000-0000-4000-8000-000000000057',
      global_roles: ['platform_admin'], memberships: [],
    } });
    return route.fulfill({ json: {} });
  });
  await page.goto('/reset');
  await expect(page.getByRole('heading', { name: 'Reset local demo data', exact: true })).toBeVisible();
}

for (const previous of ['ready', 'succeeded']) {
  test(`lost POST response checks progress through downtime after ${previous}`, async ({ page }) => {
    let requestId;
    let reads = 0;
    let posts = 0;
    await mockPage(page, async route => {
      if (route.request().method() === 'POST') {
        posts++;
        requestId = route.request().postDataJSON().request_id;
        return route.abort('failed');
      }
      if (!requestId) return route.fulfill({ json: {
        environment: 'local', status: previous,
        ...(previous === 'succeeded' ? { request_id: 'previous-job', stage: 'Previous seed restored' } : {}),
      } });
      if (++reads <= 2) return route.fulfill({ status: 503, json: { error: { code: 'unavailable' } } });
      return route.fulfill({ json: {
        environment: 'local', status: 'succeeded', request_id: requestId, stage: 'Local seed restored',
      } });
    });
    await page.getByLabel('Type RESET DEMO to confirm').fill('RESET DEMO');
    await page.getByRole('button', { name: 'Reset local data', exact: true }).click();
    await expect(page.getByText('Checking reset progress. The app may temporarily disconnect during a reset.')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Retry request', exact: true })).toHaveCount(0);
    await expect(page.getByRole('alert')).toHaveCount(0);
    await expect(page.getByText('Demo reset complete. Both applications are pending review.', { exact: true })).toBeVisible({ timeout: 20000 });
    expect(posts).toBe(1);
    await expect(page.getByRole('alert')).toHaveCount(0);
  });
}

test('a request absent from fresh status can retry with the same UUID', async ({ page }) => {
  const ids = [];
  let started = false;
  await mockPage(page, async route => {
    if (route.request().method() === 'POST') {
      ids.push(route.request().postDataJSON().request_id);
      if (ids.length === 1) return route.fulfill({ status: 503, json: { error: { code: 'unavailable' } } });
      started = true;
      return route.fulfill({ status: 202, json: {
        environment: 'local', status: 'queued', request_id: ids[0], stage: 'Queued',
      } });
    }
    return route.fulfill({ json: started
      ? { environment: 'local', status: 'succeeded', request_id: ids[0], stage: 'Done' }
      : { environment: 'local', status: 'ready' } });
  });
  await page.getByLabel('Type RESET DEMO to confirm').fill('RESET DEMO');
  await page.getByRole('button', { name: 'Reset local data', exact: true }).click();
  await expect(page.getByText('This request has not been confirmed. Retry the same request.', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Retry request', exact: true }).click();
  await expect(page.getByText('Demo reset complete. Both applications are pending review.', { exact: true })).toBeVisible();
  expect(ids).toHaveLength(2);
  expect(ids[0]).toBe(ids[1]);
  await expect(page.getByRole('alert')).toHaveCount(0);
});
