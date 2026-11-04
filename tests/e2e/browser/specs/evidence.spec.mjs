import { test, expect } from 'playwright/test';
import { api, attachIds, config, login, poll } from '../helpers.mjs';
import { uuid } from '../settings.mjs';

test('retained genuine journey has completed visit, separate payments, ready PDF and expected delivery status', async ({ page }, testInfo) => {
  test.setTimeout(420_000);
  const appointmentId = uuid(process.env, 'E2E_APPOINTMENT_ID');
  const orderId = uuid(process.env, 'E2E_ORDER_ID');
  await login(page, 'patient');
  const appointment = await api(page, `/scheduling/appointments/${appointmentId}`);
  expect(appointment.status).toBe('completed');
  const consultation = await api(page, `/billing/payments/${appointment.payment_id}`);
  expect(consultation.status).toBe('succeeded');
  expect(consultation.purpose).toBe('consultation');
  expect(consultation.appointment_id).toBe(appointmentId);
  expect(consultation.amount).toEqual(appointment.consultation_price);
  const order = await poll(() => api(page, `/fulfilment/orders/${orderId}`),
    value => value.payment_status === 'succeeded' && value.medicine_status === 'ready' && Boolean(value.delivery_id),
    'Medication payment, medicine readiness and delivery worker must produce a delivery');
  expect(order.appointment_id).toBe(appointmentId);
  expect(order.patient_id).toBe(appointment.patient_id);
  expect(order.tenant_id).toBe(appointment.tenant_id);
  const prescription = await api(page, `/clinical-records/prescriptions/${order.prescription_id}`);
  expect(prescription.status).toBe('issued');
  expect(prescription.appointment_id).toBe(appointmentId);
  expect(prescription.tenant_id).toBe(appointment.tenant_id);
  expect(prescription.patient_id).toBe(appointment.patient_id);
  const medication = await api(page, `/billing/payments/${order.payment_id}`);
  expect(medication.payment_id).not.toBe(consultation.payment_id);
  expect(medication.status).toBe('succeeded');
  expect(medication.purpose).toBe('medication_delivery');
  expect(medication.order_id).toBe(orderId);
  expect(medication.quote_id).toBe(order.quote_id);
  expect(medication.amount).toEqual(order.total);
  for (const payment of [consultation, medication]) {
    expect(payment.patient_id).toBe(appointment.patient_id);
    expect(payment.tenant_id).toBe(appointment.tenant_id);
  }
  const quote = await api(page, `/fulfilment/quotes/${order.quote_id}`);
  expect(quote.order_id).toBe(orderId);
  expect(quote.tenant_id).toBe(order.tenant_id);
  expect(quote.total).toEqual(order.total);
  expect(order.total.amount_minor).toBe(order.medication_subtotal.amount_minor + order.delivery_fee.amount_minor);
  const delivery = await poll(() => api(page, `/fulfilment/deliveries/${order.delivery_id}`),
    value => value.status === config.deliveryStatus, `Tracking must reach explicitly expected ${config.deliveryStatus}`, 90_000);
  expect(delivery.order_id).toBe(orderId);
  expect(delivery.tenant_id).toBe(order.tenant_id);
  const currentOrder = await api(page, `/fulfilment/orders/${orderId}`);
  const expectedOrderState = { submitted: 'dispatched', picked_up: 'dispatched', delivered: 'delivered', cancelled: 'exception', failed: 'exception' };
  expect(currentOrder.status).toBe(expectedOrderState[delivery.status]);
  const documents = await poll(() => api(page, `/document/documents?appointment_id=${appointmentId}&limit=100`),
    value => value.items.some(d => d.kind === 'prescription_pdf' && d.prescription_id === order.prescription_id && d.status === 'ready'),
    'Event-driven document generation must produce the matching ready prescription PDF', 90_000);
  const document = documents.items.find(d => d.kind === 'prescription_pdf' && d.prescription_id === order.prescription_id && d.status === 'ready');
  expect(document.appointment_id).toBe(appointmentId);
  expect(document.tenant_id).toBe(appointment.tenant_id);
  const download = await api(page, `/document/documents/${document.document_id}/download`);
  const url = new URL(download.download_url);
  expect(url.protocol === 'https:' || (config.target === 'local' && url.protocol === 'http:' && ['localhost', '127.0.0.1'].includes(url.hostname))).toBe(true);
  expect(Date.parse(download.expires_at)).toBeGreaterThan(Date.now());
  // An unauthenticated request checks the actual presigned object, never an RDS/S3 SDK bypass.
  const response = await page.context().request.get(url.href);
  expect(response.status(), 'Presigned PDF must be reachable from the test runner').toBe(200);
  const bytes = await response.body();
  expect(bytes.subarray(0, 5).toString()).toBe('%PDF-');
  expect(bytes.length).toBeGreaterThan(100);
  await attachIds(testInfo, { appointment_id: appointmentId, order_id: orderId,
    consultation_payment_id: consultation.payment_id, medication_payment_id: medication.payment_id,
    document_id: document.document_id, delivery_id: delivery.delivery_id,
    observed_delivery_status: delivery.status, scope: 'Read-only retained evidence; does not create or advance this journey' });
});
