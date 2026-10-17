import test from 'node:test';
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { WebSocket } from 'ws';
import { createAdmissions } from '../admission.mjs';
import { fixtureAppointments } from '../admission-server.mjs';

test('admission uses trusted participants, payment/status/window and bounded single-use leases', () => {
  let now = 1700000000000;
  const appointments = fixtureAppointments(now);
  const store = createAdmissions(appointments, { now: () => now, ttlSeconds: 60 });
  for (const id of ['unpaid', 'cancelled', 'too-early', 'too-late', 'missing']) {
    assert.throws(() => store.issue('patient-a', id));
  }
  assert.throws(() => store.issue('unrelated', 'appointment-a'));
  const a = store.issue('patient-a', 'appointment-a');
  const duplicate = store.issue('patient-a', 'appointment-a');
  const b = store.issue('doctor-a', 'appointment-a');
  assert.throws(() => store.consume(a.token, b.peerId));
  const admitted = store.consume(a.token, a.peerId);
  assert.throws(() => store.consume(duplicate.token, duplicate.peerId));
  assert.throws(() => store.consume(a.token, a.peerId));
  assert.throws(() => store.issue('patient-a', 'appointment-a'));
  store.consume(b.token, b.peerId);
  assert.equal(store.allows(admitted, { type: 'OFFER', dst: b.peerId }), true);
  appointments.get('appointment-a').payment = 'pending';
  assert.equal(store.allows(admitted, { type: 'HEARTBEAT' }), false);
  appointments.get('appointment-a').payment = 'paid';
  now += 60000;
  assert.equal(store.allows(admitted, { type: 'HEARTBEAT' }), false);
  store.release(admitted);
  const expired = store.issue('patient-a', 'appointment-a');
  now += 60000;
  assert.throws(() => store.consume(expired.token, expired.peerId));
  assert.throws(() => createAdmissions(appointments, { ttlSeconds: 301 }));
});

test('real PeerServer enforces admission and appointment isolation', { timeout: 30000 }, async (t) => {
  const child = spawn(process.execPath, ['admission-server.mjs'], {
    cwd: new URL('..', import.meta.url),
    env: { ...process.env, X02_PORT: '0', X02_TTL_SECONDS: '2' },
    stdio: ['ignore', 'pipe', 'inherit'],
  });
  const sockets = new Set();
  try {
    const base = await new Promise((resolve, reject) => {
      const timeout = setTimeout(() => reject(new Error('X02 did not start')), 10000);
      child.once('error', reject);
      child.stdout.on('data', (chunk) => {
        const match = chunk.toString().match(/http:\/\/127\.0\.0\.1:\d+/);
        if (match) { clearTimeout(timeout); resolve(match[0]); }
      });
    });
    const issue = async (subject = 'patient-a', appointmentId = 'appointment-a', expected = 200) => {
      const response = await fetch(`${base}/fixture/admissions`, {
        method: 'POST', headers: { authorization: `Bearer fixture-${subject}`, 'content-type': 'application/json' },
        // Spoofed body identity must not override the fixture-authenticated subject.
        body: JSON.stringify({ appointmentId, subject: 'doctor-a', peerId: 'chosen-id' }),
      });
      assert.equal(response.status, expected);
      return expected === 200 ? response.json() : response.text();
    };
    const connect = (grant = {}, overrides = {}, suffix = '') => new Promise((resolve, reject) => {
      const query = new URLSearchParams({ key: 'x02', id: grant.peerId || 'unknown', token: grant.token || '', ...overrides });
      const wire = new WebSocket(`${base.replace('http:', 'ws:')}/peerjs/peerjs?${query}${suffix}`);
      sockets.add(wire);
      wire.on('error', reject);
      wire.once('message', (data) => {
        assert.deepEqual(JSON.parse(data), { type: 'OPEN' });
        resolve(wire);
      });
    });
    const close = async (wire) => {
      const ended = once(wire, 'close');
      wire.close();
      await ended;
    };
    await t.test('issuer rejects unauthenticated, unrelated and ineligible requests', async () => {
      assert.equal((await fetch(`${base}/fixture/admissions`, { method: 'POST' })).status, 401);
      await issue('unrelated', 'appointment-a', 403);
      await issue('patient-b', 'appointment-a', 403);
      for (const id of ['unpaid', 'cancelled', 'too-early', 'too-late', 'missing']) await issue('patient-a', id, 403);
      assert.equal((await fetch(`${base}/peerjs/x02/peers`)).status, 401);
    });
    await t.test('handshake denies missing/tampered, wrong peer/key and duplicate parameters', async () => {
      const grant = await issue();
      await assert.rejects(connect(), /403/);
      await assert.rejects(connect(grant, { token: `${grant.token}x` }), /403/);
      await assert.rejects(connect(grant, { id: 'chosen-id' }), /403/);
      await assert.rejects(connect(grant, { key: 'x01' }), /403/);
      await assert.rejects(connect(grant, {}, '&id=other'), /403/);
      const wire = await connect(grant);
      await assert.rejects(connect(grant), /403/);
      await close(wire);
      await assert.rejects(connect(grant), /403/);
    });
    await t.test('same-appointment OFFER/ANSWER/CANDIDATE pass and rejoin needs a fresh grant', async () => {
      const a = await issue();
      const b = await issue('doctor-a');
      const caller = await connect(a);
      const receiver = await connect(b);
      for (const type of ['OFFER', 'ANSWER', 'CANDIDATE']) {
        const received = once(receiver, 'message');
        caller.send(JSON.stringify({ type, dst: b.peerId, payload: { marker: type } }));
        assert.deepEqual(JSON.parse((await received)[0]), {
          type, src: a.peerId, dst: b.peerId, payload: { marker: type },
        });
      }
      await close(caller);
      const fresh = await issue();
      assert.notEqual(fresh.peerId, a.peerId);
      await close(await connect(fresh));
      await close(receiver);
    });
    await t.test('cross-appointment frames never reach the target or the PeerServer queue', async () => {
      const b = await issue('patient-b', 'appointment-b');
      const target = await connect(b);
      const received = [];
      target.on('message', (data) => received.push(JSON.parse(data)));
      for (const type of ['OFFER', 'ANSWER', 'CANDIDATE', 'LEAVE', 'EXPIRE']) {
        const caller = await connect(await issue());
        const ended = once(caller, 'close');
        caller.send(JSON.stringify({ type, dst: b.peerId, payload: { marker: 'must-not-arrive' } }));
        assert.equal((await ended)[0], 1008);
      }
      // A round trip heartbeat/allowed offer on appointment B proves the receiver
      // remains usable after the attack, without relying on a sleep assertion.
      const doctor = await issue('doctor-b', 'appointment-b');
      const other = await connect(doctor);
      const delivered = once(target, 'message');
      other.send(JSON.stringify({ type: 'OFFER', dst: b.peerId, payload: { marker: 'allowed' } }));
      await delivered;
      assert.deepEqual(received.map((m) => m.payload.marker), ['allowed']);
      await close(other);
      await close(target);
    });
    await t.test('forged sources, unknown destinations, malformed and binary frames close the sender', async () => {
      for (const frame of [
        JSON.stringify({ type: 'HEARTBEAT', src: 'forged' }),
        JSON.stringify({ type: 'OFFER', dst: 'offline' }),
        JSON.stringify({ type: 'UNKNOWN' }), 'null', '[]', '{bad', Buffer.from('{"type":"HEARTBEAT"}'),
      ]) {
        const wire = await connect(await issue());
        const ended = once(wire, 'close');
        wire.send(frame);
        assert.equal((await ended)[0], 1008);
      }
    });
    await t.test('lease expiry closes an active socket and rejects unused expired grants', async () => {
      const expired = await issue('doctor-a');
      const wire = await connect(await issue());
      const ended = once(wire, 'close');
      assert.equal((await ended)[0], 1008);
      await assert.rejects(connect(expired), /403/);
      await close(await connect(await issue()));
    });
  } finally {
    for (const wire of sockets) wire.terminate();
    const stopped = once(child, 'exit');
    child.kill();
    await stopped;
  }
});
