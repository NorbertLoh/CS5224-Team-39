import { randomInt } from 'node:crypto';
import { expect } from 'playwright/test';
import { api, attachIds, clinic, config, login } from './helpers.mjs';

export async function prepareBooking(browser, testInfo, run) {
  expect(config.allowWrites, 'Set E2E_ALLOW_WRITES=true for this dedicated synthetic clinic').toBe(true);
  const doctorContext = await browser.newContext({ baseURL: config.baseURL, ignoreHTTPSErrors: config.ignoreHTTPSErrors });
  const patientContext = await browser.newContext({ baseURL: config.baseURL, ignoreHTTPSErrors: config.ignoreHTTPSErrors });
  const doctor = await doctorContext.newPage();
  const patient = await patientContext.newPage();
  let slot;
  let appointment;
  const ids = {};
  try {
    const identity = await login(doctor, 'doctor');
    const selected = await clinic(doctor);
    expect(identity.memberships.some(m => m.tenant_id === selected.tenant_id && m.status === 'active' && m.roles.includes('doctor'))).toBe(true);
    // A dedicated future slot avoids altering existing availability/bookings.
    const starts = (Math.ceil(Date.now() / 1_800_000) + 144 + randomInt(0, 240)) * 1_800_000;
    slot = await api(doctor, `/scheduling/clinics/${selected.tenant_id}/slots`, {
      method: 'POST', data: { starts_at: new Date(starts).toISOString(), ends_at: new Date(starts + 1_800_000).toISOString() },
    });
    Object.assign(ids, { tenant_id: selected.tenant_id, slot_id: slot.slot_id });
    await attachIds(testInfo, ids);
    await login(patient, 'patient');
    await patient.goto(`/patient/clinics/${encodeURIComponent(selected.slug)}/book`);
    const date = new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Singapore', year: 'numeric', month: '2-digit', day: '2-digit' }).format(starts);
    await patient.getByLabel('Booking date').fill(date);
    const time = new Intl.DateTimeFormat('en-SG', { timeZone: 'Asia/Singapore', hour: '2-digit', minute: '2-digit', hour12: false }).format(starts);
    // The test clinic may have other doctors at this time. Match the API-provided doctor name too.
    const directory = await api(patient, `/tenant/clinics/${selected.tenant_id}/doctors?limit=100`, { authenticated: false });
    const name = directory.items.find(item => item.doctor_id === slot.doctor_id)?.display_name;
    expect(name, 'Assigned verified test doctor must appear in the public directory').toBeTruthy();
    await patient.getByRole('button').filter({ hasText: `${time}–` }).filter({ hasText: name }).click();
    const responsePromise = patient.waitForResponse(response =>
      new URL(response.url()).pathname === `${config.apiPath}/scheduling/appointments` && response.request().method() === 'POST');
    await patient.getByRole('button', { name: 'Continue to checkout', exact: true }).click();
    const response = await responsePromise;
    expect(response.status()).toBe(201);
    appointment = await response.json();
    ids.appointment_id = appointment.appointment_id;
    await attachIds(testInfo, ids);
    expect(appointment.slot_id).toBe(slot.slot_id);
    expect(appointment.tenant_id).toBe(selected.tenant_id);
    expect(appointment.status).toBe('held');
    expect(appointment.consultation_price).toEqual(slot.consultation_price);
    await expect(patient.getByRole('heading', { name: 'Booking hold', exact: true })).toBeVisible();
    await run({ patient, doctor, appointment, selected, ids });
  } catch (error) {
    for (const [role, page] of [['patient', patient], ['doctor', doctor]]) {
      const screenshot = await page.screenshot({ mask: [page.locator('input[type=password]')] }).catch(() => null);
      if (screenshot) await testInfo.attach(`${role}-failure`, { body: screenshot, contentType: 'image/png' });
    }
    throw error;
  } finally {
    // Financial/uncertain outcomes are retained for review; only unpaid holds are released.
    // If setup failed before receiving an appointment ID, do not guess or delete its slot.
    try {
      if (appointment) {
        if (new URL(patient.url()).origin !== config.baseURL)
          await patient.goto(`/patient/checkout?appointment_id=${appointment.appointment_id}`);
        const current = await api(patient, `/scheduling/appointments/${appointment.appointment_id}`);
        if (current.status === 'held' && !current.payment_id) {
          await api(patient, `/scheduling/appointments/${appointment.appointment_id}/cancel`, {
            method: 'POST', data: { reason: 'I05 synthetic E2E unpaid booking cleanup.' },
          });
          await api(doctor, `/scheduling/slots/${slot.slot_id}`, { method: 'DELETE' });
          ids.cleanup = 'Unpaid hold cancelled and test slot removed';
        } else if (current.status === 'cancelled' && !current.payment_id) {
          await api(doctor, `/scheduling/slots/${slot.slot_id}`, { method: 'DELETE' });
          ids.cleanup = 'Cancelled unpaid test slot removed';
        } else ids.cleanup = 'Retained appointment/slot: inspect payment and appointment outcome before cleanup';
      } else if (slot) ids.cleanup = 'Retained slot: setup incomplete; inspect for a booking before removal';
    } catch {
      ids.cleanup = 'Cleanup failed: inspect retained resource IDs using normal application APIs';
      // Cleanup is part of acceptance, not a hidden warning.
      testInfo.annotations.push({ type: 'cleanup-failed', description: ids.cleanup });
      await attachIds(testInfo, ids);
      throw new Error(ids.cleanup);
    } finally {
      await attachIds(testInfo, ids);
      await patientContext.close();
      await doctorContext.close();
    }
  }
}
