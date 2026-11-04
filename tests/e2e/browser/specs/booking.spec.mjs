import { test, expect } from 'playwright/test';
import { api, poll } from '../helpers.mjs';
import { prepareBooking } from '../booking.mjs';

test('doctor availability → patient browser booking → release → slot available again', async ({ browser }, testInfo) => {
  await prepareBooking(browser, testInfo, async ({ patient, appointment, selected }) => {
    const detail = await api(patient, `/scheduling/appointments/${appointment.appointment_id}`);
    expect(detail.status).toBe('held');
    await patient.getByRole('button', { name: 'Release booking and change time', exact: true }).click();
    await expect(patient.getByRole('heading', { name: 'Choose a time', exact: true })).toBeVisible();
    await poll(() => api(patient, `/scheduling/appointments/${appointment.appointment_id}`),
      value => value.status === 'cancelled', 'Unpaid booking must be cancelled');
    const query = new URLSearchParams({ from: appointment.starts_at, to: appointment.ends_at, doctor_id: appointment.doctor_id, limit: '100' });
    const slots = await api(patient, `/scheduling/clinics/${selected.tenant_id}/slots?${query}`, { authenticated: false });
    expect(slots.items.find(s => s.slot_id === appointment.slot_id)?.availability).toBe('available');
  });
});
