import { test, expect } from 'playwright/test';
import { api, attachIds, config, poll } from '../helpers.mjs';
import { prepareBooking } from '../booking.mjs';

test('hosted Stripe test Checkout → genuine webhook → confirmed booking', async ({ browser }, testInfo) => {
  expect(testInfo.project.use.headless, 'Run npm run test:stripe with a headed browser for the payment handoff').toBe(false);
  expect(config.stripeTestMode, 'Confirm backend Stripe test-mode setup with E2E_STRIPE_TEST_MODE=true').toBe(true);
  test.setTimeout((config.paymentWaitSeconds + 120) * 1000);
  await prepareBooking(browser, testInfo, async ({ patient, doctor, appointment, ids }) => {
    await patient.getByRole('link', { name: 'Continue to payment', exact: true }).click();
    await patient.getByRole('button', { name: 'Continue to secure checkout', exact: true }).click();
    await patient.waitForURL(url => url.protocol === 'https:' && url.hostname === 'checkout.stripe.com');
    // Fail before payment if an unexpected live Checkout is returned.
    expect(patient.url(), 'Only hosted test Checkout is permitted').toContain('cs_test_');
    console.log('Complete the visible Stripe TEST checkout using 4242 4242 4242 4242, a future expiry and three-digit CVC. Waiting for return and verified confirmation.');
    await patient.waitForURL(url => url.origin === config.baseURL, { timeout: config.paymentWaitSeconds * 1000 });
    const confirmed = await poll(() => api(patient, `/scheduling/appointments/${appointment.appointment_id}`),
      value => value.status === 'confirmed' && value.payment_resolution === 'confirmed',
      'Genuine webhook and deployed payment workers must confirm the booking');
    const payment = await api(patient, `/billing/payments/${confirmed.payment_id}`);
    Object.assign(ids, { payment_id: payment.payment_id, cleanup: 'Paid booking retained for consultation and audit; not automatically refunded' });
    await attachIds(testInfo, ids);
    expect(payment.status).toBe('succeeded');
    expect(payment.purpose).toBe('consultation');
    expect(payment.appointment_id).toBe(appointment.appointment_id);
    expect(payment.patient_id).toBe(confirmed.patient_id);
    expect(payment.tenant_id).toBe(confirmed.tenant_id);
    expect(payment.amount).toEqual(appointment.consultation_price);
    const doctorView = await api(doctor, `/scheduling/appointments/${appointment.appointment_id}`);
    expect(doctorView.status).toBe('confirmed');
    await patient.goto(`/patient/checkout?appointment_id=${appointment.appointment_id}`);
    await expect(patient.getByRole('heading', { name: 'Appointment confirmed', exact: true })).toBeVisible();
  });
});
