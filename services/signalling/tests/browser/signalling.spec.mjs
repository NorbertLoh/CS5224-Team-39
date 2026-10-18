import { test, expect } from '@playwright/test';
import { fileURLToPath } from 'node:url';

test('packaged PeerServer through Caddy HTTPS/WSS supports admitted PeerJS data and fresh rejoin', async ({ browser }) => {
  const context = await browser.newContext({ ignoreHTTPSErrors: true, permissions: ['camera', 'microphone'] });
  try {
    const patient = await context.newPage();
    const doctor = await context.newPage();
    const start = async (page, subject) => {
      await page.goto('https://localhost:8443/');
      await page.addScriptTag({ path: fileURLToPath(new URL('../../node_modules/peerjs/dist/peerjs.min.js', import.meta.url)) });
      return page.evaluate(async (subject) => {
        window.stream = await navigator.mediaDevices.getUserMedia({ audio: true, video: true });
        const response = await fetch('/api/v1/consultation/admissions', {
          method: 'POST', headers: { authorization: `Bearer fixture-${subject}`, 'content-type': 'application/json' },
          body: JSON.stringify({ appointment_id: 'a' }),
        });
        if (response.status !== 201) throw new Error(`Fixture admission: ${response.status}`);
        const grant = await response.json();
        window.received = [];
        window.peer = new Peer(grant.peer_id, { host: 'localhost', port: 8443, secure: true,
          path: '/peerjs', key: 'telelink', token: grant.token, config: { iceServers: [] } });
        window.peer.on('connection', (connection) => connection.on('data', (data) => {
          window.received.push(data); connection.send(`echo:${data}`);
        }));
        return new Promise((resolve, reject) => {
          const timeout = setTimeout(() => reject(new Error('WSS peer did not open')), 10000);
          window.peer.on('open', () => { clearTimeout(timeout); resolve(grant.peer_id); });
          window.peer.on('error', reject);
        });
      }, subject);
    };
    const first = await start(patient, 'patient-a');
    const doctorId = await start(doctor, 'doctor-a');
    const exchange = async (marker) => {
      const result = await patient.evaluate(({ doctorId, marker }) => new Promise((resolve, reject) => {
        const connection = window.peer.connect(doctorId, { reliable: true });
        const timeout = setTimeout(() => reject(new Error('Data channel did not exchange data')), 10000);
        connection.on('open', () => connection.send(marker));
        connection.on('data', (data) => { clearTimeout(timeout); resolve(data); });
        connection.on('error', reject);
      }), { doctorId, marker });
      expect(result).toBe(`echo:${marker}`);
      await expect.poll(() => doctor.evaluate(() => window.received)).toContain(marker);
    };
    await exchange('tls-first-join');
    await patient.evaluate(() => { window.peer.destroy(); window.stream.getTracks().forEach((track) => track.stop()); });
    await expect.poll(async () => (await patient.request.post('https://localhost:8443/api/v1/consultation/admissions', {
      headers: { authorization: 'Bearer fixture-patient-a' }, data: { appointment_id: 'a' },
    })).status()).toBe(201);
    expect(await start(patient, 'patient-a')).not.toBe(first);
    await exchange('tls-rejoin');
    for (const page of [patient, doctor]) await page.evaluate(() => {
      window.peer.destroy(); window.stream.getTracks().forEach((track) => track.stop());
    });
    for (const path of ['/api/v1/consultation/internal/admissions/consume', '/fixture/admissions']) {
      expect((await patient.request.post(`https://localhost:8443${path}`, { data: {} })).status()).toBe(404);
    }
  } finally { await context.close(); }
});
