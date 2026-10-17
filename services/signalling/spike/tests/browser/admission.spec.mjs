import { test, expect } from '@playwright/test';

test('admitted PeerJS clients establish a real data channel and rejoin with a fresh identity', async ({ browser }) => {
  const context = await browser.newContext({ permissions: ['camera', 'microphone'] });
  try {
    const patient = await context.newPage();
    const doctor = await context.newPage();
    const start = async (page, subject) => {
      await page.goto('http://127.0.0.1:9002');
      return page.evaluate(async (subject) => {
        // Match the consultation's camera permission so local host ICE candidates
        // are available on Windows as well as CI; no media leaves this fixture.
        window.localStream = await navigator.mediaDevices.getUserMedia({ audio: true, video: true });
        const response = await fetch('/fixture/admissions', {
          method: 'POST', headers: { authorization: `Bearer fixture-${subject}`, 'content-type': 'application/json' },
          body: JSON.stringify({ appointmentId: 'appointment-a' }),
        });
        if (!response.ok) throw new Error(`Admission: ${response.status}`);
        const grant = await response.json();
        window.peer = new Peer(grant.peerId, {
          host: '127.0.0.1', port: 9002, path: '/peerjs', key: 'x02', token: grant.token,
          secure: false, config: { iceServers: [] },
        });
        window.received = [];
        window.peer.on('connection', (connection) => {
          connection.on('data', (data) => {
            window.received.push(data);
            connection.send(`echo:${data}`);
          });
        });
        return new Promise((resolve, reject) => {
          const timeout = setTimeout(() => reject(new Error('Peer admission did not open')), 8000);
          window.peer.on('open', () => { clearTimeout(timeout); resolve(grant.peerId); });
          window.peer.on('error', reject);
        });
      }, subject);
    };
    await start(patient, 'patient-a');
    const doctorId = await start(doctor, 'doctor-a');
    const exchange = async (marker) => {
      const reply = await patient.evaluate(({ doctorId, marker }) => new Promise((resolve, reject) => {
        const connection = window.peer.connect(doctorId, { reliable: true });
        const timeout = setTimeout(() => reject(new Error(`Data channel did not exchange data: ${connection.peerConnection?.connectionState}/${connection.peerConnection?.iceConnectionState}; peer open=${window.peer.open}`)), 8000);
        connection.on('open', () => connection.send(marker));
        connection.on('data', (data) => { clearTimeout(timeout); resolve(data); });
        connection.on('error', reject);
        window.peer.on('error', reject);
      }), { doctorId, marker });
      expect(reply).toBe(`echo:${marker}`);
      await expect.poll(() => doctor.evaluate(() => window.received)).toContain(marker);
    };
    await exchange('first-join');
    await patient.evaluate(() => window.peer.destroy());
    // Wait for the server to release the participant slot, then prove fresh join.
    await expect.poll(async () => {
      const response = await patient.request.post('http://127.0.0.1:9002/fixture/admissions', {
        headers: { authorization: 'Bearer fixture-patient-a' }, data: { appointmentId: 'appointment-a' },
      });
      return response.status();
    }).toBe(200);
    await start(patient, 'patient-a');
    await exchange('rejoined');
    await patient.evaluate(() => window.peer.destroy());
    await patient.evaluate(() => window.localStream.getTracks().forEach((track) => track.stop()));
    await doctor.evaluate(() => window.peer.destroy());
    await doctor.evaluate(() => window.localStream.getTracks().forEach((track) => track.stop()));
  } finally { await context.close(); }
});
