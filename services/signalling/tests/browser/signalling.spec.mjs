import { test, expect } from '@playwright/test';
import { fileURLToPath } from 'node:url';

test('two-way media and the same PeerJS connection survive the 60-second join deadline', async ({ browser }) => {
  test.setTimeout(100000);
  const context = await browser.newContext({ ignoreHTTPSErrors: true, permissions: ['camera', 'microphone'] });
  try {
    const patient = await context.newPage();
    const doctor = await context.newPage();
    const join = async (page, subject) => {
      await page.goto('https://localhost:8443/');
      await page.addScriptTag({ path: fileURLToPath(new URL('../../node_modules/peerjs/dist/peerjs.min.js', import.meta.url)) });
      return page.evaluate(async ({ subject, relay }) => {
        const grant = await (await fetch('/api/v1/consultation/admissions', {
          method: 'POST', headers: { authorization: `Bearer fixture-${subject}`, 'content-type': 'application/json' },
          body: JSON.stringify({ appointment_id: 'a' }),
        })).json();
        window.grant = grant;
        window.subject = subject;
        window.renewals = 0;
        window.disconnects = 0;
        window.stream = await navigator.mediaDevices.getUserMedia({ audio: true, video: true });
        if (relay && (!grant.relay_only || !grant.ice_servers?.length)) throw new Error('TURN fixture missing');
        window.peer = new Peer(grant.peer_id, { host: 'localhost', port: 8443, secure: true,
          path: '/peerjs', key: 'telelink', token: grant.token,
          config: { iceServers: grant.ice_servers || [], iceTransportPolicy: grant.relay_only ? 'relay' : 'all' } });
        window.peer.on('disconnected', () => window.disconnects++);
        window.peer.on('call', (call) => { window.call = call; call.answer(window.stream); });
        await new Promise((resolve, reject) => { window.peer.once('open', resolve); window.peer.once('error', reject); });
        window.renewTimer = setInterval(async () => {
          try {
            const response = await fetch('/api/v1/consultation/admissions/renew', {
              method: 'POST', headers: { authorization: `Bearer fixture-${subject}`, 'content-type': 'application/json' },
              body: JSON.stringify({ peer_id: grant.peer_id, token: grant.token }),
            });
            if (!response.ok) throw new Error('Renewal rejected');
            window.renewals++;
          } catch { window.renewError = true; }
        }, 10000);
        return { id: grant.peer_id, deadline: Date.parse(grant.expires_at) };
      }, { subject, relay: Boolean(process.env.RF30_TEST_TURN_URL) });
    };
    const receiver = await join(doctor, 'doctor-a');
    const caller = await join(patient, 'patient-a');
    await patient.evaluate((id) => { window.call = window.peer.call(id, window.stream); }, receiver.id);
    const stats = (page) => page.evaluate(async () => {
      const pc = window.call?.peerConnection;
      if (!pc) return null;
      const reports = await pc.getStats();
      const incoming = [...reports.values()].filter((r) => r.type === 'inbound-rtp');
      const transport = [...reports.values()].find((r) => r.type === 'transport' && r.selectedCandidatePairId);
      const pair = transport && reports.get(transport.selectedCandidatePairId);
      return { id: window.peer.id, state: pc.connectionState, disconnects: window.disconnects,
        renewals: window.renewals, failed: Boolean(window.renewError),
        audio: incoming.find((r) => r.kind === 'audio')?.bytesReceived || 0,
        video: incoming.find((r) => r.kind === 'video')?.bytesReceived || 0,
        candidate: pair && reports.get(pair.localCandidateId)?.candidateType };
    });
    for (const page of [patient, doctor]) {
      await expect.poll(async () => (await stats(page))?.state).toBe('connected');
      await expect.poll(async () => (await stats(page))?.video || 0).toBeGreaterThan(0);
      if (process.env.RF30_TEST_TURN_URL) await expect.poll(async () => (await stats(page))?.candidate).toBe('relay');
    }
    const before = await Promise.all([stats(patient), stats(doctor)]);
    // Real elapsed time and RTP prove the allocation/connection crosses join expiry.
    await patient.waitForTimeout(Math.max(caller.deadline, receiver.deadline) - Date.now() + 5000);
    const after = await Promise.all([stats(patient), stats(doctor)]);
    for (let i = 0; i < after.length; i++) {
      expect(after[i].id).toBe(before[i].id);
      expect(after[i].state).toBe('connected');
      expect(after[i].disconnects).toBe(0);
      expect(after[i].failed).toBe(false);
      expect(after[i].renewals).toBeGreaterThanOrEqual(6);
      expect(after[i].audio).toBeGreaterThan(before[i].audio);
      expect(after[i].video).toBeGreaterThan(before[i].video);
    }
  } finally { await context.close(); }
});

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
