import { test, expect } from 'playwright/test';
import { api, clinic, login } from '../helpers.mjs';

test('public directory and clinic storefront load through deployed ingress', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Your clinic, wherever you are.' })).toBeVisible();
  const list = await api(page, '/tenant/clinics?limit=25', { authenticated: false });
  expect(Array.isArray(list.items)).toBe(true);
  const selected = await clinic(page);
  await page.goto(`/clinics/${encodeURIComponent(selected.slug)}`);
  await expect(page.getByText(`Welcome to ${selected.name}.`, { exact: true })).toBeVisible();
  const doctors = await api(page, `/tenant/clinics/${selected.tenant_id}/doctors?limit=25`, { authenticated: false });
  expect(doctors.items.length, 'Dedicated clinic needs at least one approved doctor').toBeGreaterThan(0);
});

test('patient signs in and loads appointments, profile, prescriptions and documents', async ({ page }) => {
  await login(page, 'patient');
  for (const path of ['/scheduling/appointments?limit=25', '/identity/me/patient-profile',
    '/document/documents?limit=25', '/clinical-records/prescriptions?limit=25',
    '/fulfilment/orders?limit=25', '/billing/payments?limit=25']) await api(page, path);
  for (const [path, heading] of [
    ['/patient', 'Patient'], ['/patient/profile', 'My profile'],
    ['/patient/prescriptions', 'Prescriptions & medicines'], ['/patient/documents', 'Documents'],
  ]) {
    await page.goto(path);
    await expect(page.getByRole('heading', { name: heading, exact: true }).first()).toBeVisible();
    await expect(page.getByRole('alert')).toHaveCount(0);
  }
});

test('verified doctor signs in and loads clinic appointments and availability', async ({ page }) => {
  const identity = await login(page, 'doctor');
  const selected = await clinic(page);
  expect(identity.memberships.some(m => m.tenant_id === selected.tenant_id && m.status === 'active' && m.roles.includes('doctor'))).toBe(true);
  await page.goto(`/doctor/clinics/${selected.tenant_id}`);
  await expect(page.getByRole('heading', { name: 'Appointments', exact: true })).toBeVisible();
  await api(page, `/scheduling/appointments?tenant_id=${selected.tenant_id}&view_role=doctor&limit=25`);
  await page.goto(`/doctor/clinics/${selected.tenant_id}/availability`);
  await expect(page.getByRole('heading', { name: 'Your availability', exact: true })).toBeVisible();
});

test('clinic admin signs in and reads clinic settings, orders and payments', async ({ page }) => {
  const identity = await login(page, 'clinic_admin');
  const selected = await clinic(page);
  expect(identity.memberships.some(m => m.tenant_id === selected.tenant_id && m.status === 'active' && m.roles.includes('clinic_admin'))).toBe(true);
  await page.goto(`/clinic-admin/clinics/${selected.tenant_id}/appointments`);
  await expect(page.getByRole('heading', { name: 'Clinic appointments', exact: true })).toBeVisible();
  for (const path of [
    `/tenant/clinics/${selected.tenant_id}/location`,
    `/fulfilment/orders?tenant_id=${selected.tenant_id}&limit=25`,
    `/billing/payments?tenant_id=${selected.tenant_id}&limit=25`,
  ]) await api(page, path);
});

test('platform admin signs in and reads clinic and doctor review queues', async ({ page }) => {
  await login(page, 'platform_admin');
  await page.goto('/platform-admin/clinics');
  await expect(page.getByRole('heading', { name: 'Platform clinics', exact: true })).toBeVisible();
  await api(page, '/tenant/admin/clinics?limit=25');
  await api(page, '/identity/platform/doctor-applications?limit=25');
});
