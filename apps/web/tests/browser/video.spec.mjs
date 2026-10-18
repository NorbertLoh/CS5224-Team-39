import { test, expect } from '@playwright/test';

const base = 'https://localhost:8443';
const appointment = { appointment_id: 'u11-appointment', tenant_id: 'u11-clinic', patient_id: 'u11-patient',
  doctor_id: 'u11-doctor', slot_id: 'u11-slot', status: 'in_progress',
  starts_at: '2026-10-18T10:00:00Z', ends_at: '2026-10-18T10:30:00Z',
  hold_expires_at: null, consultation_price: { amount_minor: 5000, currency: 'SGD' },
  payment_id: 'u11-payment', payment_resolution: 'confirmed', created_at: '2026-10-18T09:00:00Z', updated_at: '2026-10-18T09:00:00Z' };

async function setup(browser) {
  const context = await browser.newContext({ ignoreHTTPSErrors: true, permissions: ['camera', 'microphone'] });
  await context.request.get(`${base}/u11-fixture/reset`);
  await context.addInitScript(() => {
    window.__streams = []; window.__pcs = []; window.__wire = [];
    const WS = window.WebSocket;
    window.WebSocket = class extends WS {
      constructor(...args) { super(...args); this.addEventListener('close', (event) => window.__wire.push({ close: event.code })); }
      send(data) { try { window.__wire.push({ send: JSON.parse(data).type }); } catch { /* test diagnostics only */ } super.send(data); }
    };
    const original = navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
    navigator.mediaDevices.getUserMedia = async (options) => {
      const stream = await original(options); window.__streams.push(stream); return stream;
    };
    const PC = window.RTCPeerConnection;
    window.RTCPeerConnection = class extends PC {
      constructor(...args) { super(...args); window.__pcs.push(this); }
    };
  });
  await context.route('**/api/v1/**', async (route) => {
    const path = new URL(route.request().url()).pathname;
    let json = { items: [], next_cursor: null };
    let status = 200;
    if (path.endsWith('/identity/me')) json = { subject_id: 'u11-doctor', global_roles: [],
      memberships: [{ tenant_id: 'u11-clinic', roles: ['doctor'], status: 'active' }] };
    else if (path.endsWith('/scheduling/appointments')) json = { items: [appointment], next_cursor: null };
    else if (path.endsWith('/scheduling/appointments/u11-appointment')) json = appointment;
    else if (path.endsWith('/note')) { status = 404; json = { error: { code: 'not_found' } }; }
    await route.fulfill({ status, json });
  });
  const patient = await context.newPage();
  const doctor = await context.newPage();
  const errors = [];
  for (const page of [patient, doctor]) page.on('pageerror', (error) => errors.push(error.message));
  return { context, patient, doctor, errors };
}

async function open(page, role, suffix = '') {
  await page.goto(`${base}/tests/browser/room.html?role=${role}${suffix}`);
  await expect(page.getByRole('button', { name: 'Join consultation', exact: true })).toBeVisible();
}

async function join(patient, doctor) {
  await doctor.getByRole('button', { name: /^(Join|Rejoin) consultation$/ }).click();
  await expect(doctor.locator('[aria-label="Video call"]').getByRole('status')).toHaveText('Waiting room');
  await patient.getByRole('button', { name: /^(Join|Rejoin) consultation$/ }).click();
  for (const page of [patient, doctor]) {
    await expect(page.locator('[aria-label="Video call"]').getByRole('status')).toHaveText('Connected', { timeout: 15000 });
    await expect.poll(() => page.locator('video[aria-label^="Remote"]').evaluate((video) =>
      video.videoWidth > 0 && video.currentTime > 0)).toBe(true);
    await expect.poll(() => page.evaluate(async () => {
      const pc = window.__pcs.findLast((pc) => pc.connectionState === 'connected');
      if (!pc) return false;
      const stats = [...(await pc.getStats()).values()];
      return ['audio', 'video'].every((kind) => stats.some((s) => s.type === 'inbound-rtp' && s.kind === kind && s.bytesReceived > 0)
        && stats.some((s) => s.type === 'outbound-rtp' && s.kind === kind && s.bytesSent > 0));
    })).toBe(true);
  }
}

async function stopped(page) {
  await expect.poll(() => page.evaluate(() => window.__streams.every((s) => s.getTracks().every((t) => t.readyState === 'ended'))
    && window.__pcs.every((pc) => pc.connectionState === 'closed'))).toBe(true);
}

test('room exchanges actual audio/video, toggles devices and rejoins while retaining doctor notes', async ({ browser }) => {
  const { context, patient, doctor, errors } = await setup(browser);
  try {
    await open(patient, 'patient'); await open(doctor, 'doctor');
    await expect(patient.getByRole('complementary', { name: 'Doctor workspace' })).toHaveCount(0);
    await expect(doctor.getByRole('combobox', { name: /Appointment/ })).toBeVisible();
    await doctor.getByRole('combobox', { name: /Appointment/ }).selectOption('u11-appointment', { timeout: 5000 });
    await expect(doctor.getByRole('textbox', { name: /^Consultation note/ })).toBeVisible();
    await doctor.getByRole('textbox', { name: /^Consultation note/ }).fill('Unsaved note stays during call transitions');
    await join(patient, doctor);
    await patient.getByRole('button', { name: 'Mute microphone' }).click();
    await patient.getByRole('button', { name: 'Turn camera off' }).click();
    expect(await patient.evaluate(() => window.__streams.at(-1).getTracks().every((track) => !track.enabled))).toBe(true);
    await patient.getByRole('button', { name: 'Unmute microphone' }).click();
    await patient.getByRole('button', { name: 'Turn camera on' }).click();
    if (process.env.U11_TURN_URL) {
      for (const page of [patient, doctor]) expect(await page.evaluate(async () => {
        const stats = await window.__pcs.at(-1).getStats();
        const pair = [...stats.values()].find((s) => s.type === 'candidate-pair' && s.state === 'succeeded' && s.nominated);
        return pair && stats.get(pair.localCandidateId)?.candidateType;
      })).toBe('relay');
    }
    await patient.getByRole('button', { name: 'Leave call' }).click();
    await stopped(patient);
    await expect(doctor.locator('[aria-label="Video call"]').getByRole('status')).toHaveText('Disconnected');
    await stopped(doctor);
    await expect(doctor.getByRole('textbox', { name: /^Consultation note/ })).toHaveValue('Unsaved note stays during call transitions');
    await join(patient, doctor);
    await doctor.keyboard.press('Escape');
    await stopped(doctor); await stopped(patient);
    await expect(doctor.getByRole('button', { name: 'Rejoin consultation' })).toBeFocused();
    expect(errors).toEqual([]);
  } catch (error) {
    for (const page of [patient, doctor]) console.log('U11 redacted diagnostics', await page.evaluate(() => ({ wire: window.__wire, pcs: window.__pcs.map((pc) => pc.connectionState) })));
    throw error;
  } finally { await context.close(); }
});

test('signalling revocation stops media and expiry requires fresh access', async ({ browser }) => {
  const { context, patient, doctor } = await setup(browser);
  try {
    await open(patient, 'patient'); await open(doctor, 'doctor'); await join(patient, doctor);
    await context.request.get(`${base}/u11-fixture/revoke`);
    for (const page of [patient, doctor]) {
      await expect(page.locator('[aria-label="Video call"]').getByRole('status')).toHaveText('Disconnected');
      await stopped(page);
    }
    await context.request.get(`${base}/u11-fixture/reset`);
    await open(patient, 'patient', '&shortLease=1');
    await patient.getByRole('button', { name: 'Join consultation', exact: true }).click();
    await expect(patient.getByRole('alert')).toContainText('access expired');
    await stopped(patient);
  } finally { await context.close(); }
});

test('permission denial, device loss, mobile layout and navigation clean up', async ({ browser }) => {
  const { context, patient, doctor } = await setup(browser);
  try {
    await open(patient, 'patient');
    await patient.evaluate(() => { navigator.mediaDevices.getUserMedia = () => Promise.reject(new DOMException('', 'NotAllowedError')); });
    await patient.getByRole('button', { name: 'Join consultation', exact: true }).click();
    await expect(patient.getByRole('alert')).toContainText('permission was denied');
    await open(patient, 'patient'); await open(doctor, 'doctor'); await join(patient, doctor);
    await patient.evaluate(() => window.__streams.at(-1).getVideoTracks()[0].dispatchEvent(new Event('ended')));
    await expect(patient.getByRole('alert')).toContainText('disconnected');
    await stopped(patient); await stopped(doctor);
    await doctor.setViewportSize({ width: 390, height: 844 });
    expect(await doctor.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await patient.getByRole('button', { name: 'Rejoin consultation' }).click();
    await patient.goto(`${base}/tests/browser/room.html?role=patient`);
    await expect(patient.getByRole('button', { name: 'Join consultation', exact: true })).toBeVisible();
    expect(await patient.evaluate(() => window.__streams.length)).toBe(0);
  } finally { await context.close(); }
});
