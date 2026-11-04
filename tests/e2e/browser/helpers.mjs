import { expect } from 'playwright/test';
import { credentials, required, settings } from './settings.mjs';

export const config = settings();

export async function login(page, role) {
  const { email, password } = credentials(role);
  await page.goto('/sign-in');
  const form = page.getByRole('form', { name: 'Sign in', exact: true });
  await form.getByLabel('Email address').fill(email);
  await form.getByLabel('Password', { exact: true }).fill(password);
  await form.getByRole('button', { name: 'Sign in', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Sign out', exact: true })).toBeVisible();
  const identity = await api(page, '/identity/me');
  const allowed = ['doctor', 'clinic_admin'].includes(role)
    ? identity.memberships.some(m => m.status === 'active' && m.roles.includes(role))
    : identity.global_roles.includes(role);
  expect(allowed, `${role} account needs its effective role (doctors require verification)`).toBe(true);
  return identity;
}

// Use browser fetch so requests traverse the same public ingress, TLS and auth as the app.
// Tokens never leave the browser context or appear in assertion/report payloads.
export async function api(page, path, { method = 'GET', data, authenticated = true } = {}) {
  const result = await page.evaluate(async ({ path, method, data, authenticated, apiPath }) => {
    const session = JSON.parse(localStorage.getItem('telelink.session') || 'null');
    const headers = {};
    if (authenticated) {
      if (!session?.accessToken) return { status: 0, error: 'No browser session' };
      headers.Authorization = `Bearer ${session.accessToken}`;
    }
    if (data !== undefined) headers['Content-Type'] = 'application/json';
    const response = await fetch(apiPath + path, {
      method, headers, body: data === undefined ? undefined : JSON.stringify(data),
      signal: AbortSignal.timeout(20_000), redirect: 'error', cache: 'no-store',
    });
    if (!response.ok) return { status: response.status };
    return { status: response.status, data: response.status === 204 ? null : await response.json() };
  }, { path, method, data, authenticated, apiPath: config.apiPath });
  expect(result.status, `${method} ${path} through public ingress`).toBeGreaterThanOrEqual(200);
  expect(result.status, `${method} ${path} through public ingress`).toBeLessThan(300);
  return result.data;
}

export async function clinic(page) {
  const slug = required(process.env, 'E2E_CLINIC_SLUG');
  const result = await api(page, `/tenant/clinics/by-slug/${encodeURIComponent(slug)}`, { authenticated: false });
  expect(result.status).toBe('active');
  return result;
}

export async function attachIds(testInfo, ids) {
  await testInfo.attach('resource-ids', { body: JSON.stringify(ids, null, 2), contentType: 'application/json' });
}

export async function poll(read, accept, description, timeout = 120_000) {
  let result;
  await expect.poll(async () => {
    result = await read();
    return accept(result);
  }, { message: description, timeout, intervals: [1000, 2000, 5000] }).toBe(true);
  return result;
}
