import test from 'node:test';
import assert from 'node:assert/strict';
import { once } from 'node:events';
import { randomUUID } from 'node:crypto';
import { setTimeout as delay } from 'node:timers/promises';
import { WebSocket } from 'ws';
import { createServer } from '../src/server.mjs';
import { configuration } from '../src/config.mjs';
import { fixtures, SECRET } from './fixtures.mjs';

test('configuration requires scoped secrets, exact HTTPS origins and production HTTPS upstream', () => {
  for (const changes of [{ SIGNALLING_SECRET: '' }, { SIGNALLING_SECRET: 'short' },
    { SIGNALLING_ORIGINS: '*' }, { SIGNALLING_ORIGINS: 'https://localhost/path' },
    { SIGNALLING_ENVIRONMENT: 'production' }, { CONSULTATION_URL: 'http://user:pass@localhost' }]) {
    assert.throws(() => configuration({ SIGNALLING_SECRET: SECRET, ...changes }));
  }
  assert.equal(configuration({ SIGNALLING_SECRET: SECRET }).host, '127.0.0.1');
});

async function setup(t, options = {}) {
  const fixture = fixtures(options);
  fixture.server.listen(0, '127.0.0.1');
  await once(fixture.server, 'listening');
  const config = configuration({ SIGNALLING_SECRET: SECRET,
    CONSULTATION_URL: `http://127.0.0.1:${fixture.server.address().port}` });
  config.checkIntervalMs = 30;
  const server = createServer(config);
  server.listen(0, '127.0.0.1');
  await once(server, 'listening');
  const base = `http://127.0.0.1:${server.address().port}`;
  const sockets = new Set();
  t.after(async () => {
    server.drain();
    for (const wire of sockets) wire.terminate();
    await new Promise((resolve) => server.close(resolve));
    fixture.server.closeAllConnections();
    await new Promise((resolve) => fixture.server.close(resolve));
  });
  const connect = (grant = {}, changes = {}, origin = 'https://localhost:8443', suffix = '') => new Promise((resolve, reject) => {
    const query = new URLSearchParams({ key: 'telelink', id: grant.peer_id || randomUUID(), token: grant.token || '', ...changes });
    const wire = new WebSocket(`${base.replace('http:', 'ws:')}/peerjs/peerjs?${query}${suffix}`, { origin });
    sockets.add(wire);
    wire.on('error', reject);
    wire.once('message', (data) => { assert.deepEqual(JSON.parse(data), { type: 'OPEN' }); resolve(wire); });
  });
  return { ...fixture, connect, base, server };
}

async function close(wire) {
  const ended = once(wire, 'close'); wire.close(); await ended;
}

async function released(api, grant) {
  for (let i = 0; i < 75 && !api.grants.get(grant.token).released; i++) await delay(10);
  assert.equal(api.grants.get(grant.token).released, true);
}

test('real HTTP admission consumption precedes PeerServer registration and prevents replay', async (t) => {
  const api = await setup(t);
  assert.equal((await fetch(`${api.base}/peerjs/telelink/id`)).status, 403);
  assert.equal((await fetch(`${api.base}/peerjs/telelink/peers`)).status, 403);
  assert.equal((await fetch(`${api.base}/fixture/admissions`, { method: 'POST' })).status, 404);
  const grant = api.issue();
  await assert.rejects(api.connect(), /403/);
  await assert.rejects(api.connect(grant, { id: randomUUID() }), /403/);
  await assert.rejects(api.connect(grant, { key: 'other' }), /403/);
  await assert.rejects(api.connect(grant, {}, 'https://evil.test'), /403/);
  await assert.rejects(api.connect(grant, {}, undefined, '&id=duplicate'), /403/);
  const wire = await api.connect(grant);
  assert.equal(api.state.consumes, 1);
  await assert.rejects(api.connect(grant), /403/);
  await close(wire);
  await assert.rejects(api.connect(grant), /403/);
});

test('V04 discovery returns only the live distinct participant in the same appointment', async (t) => {
  const api = await setup(t);
  const patient = api.issue();
  const doctor = api.issue('doctor-a');
  const discover = (grant, origin = 'https://localhost:8443', extra = {}) => fetch(`${api.base}/peerjs/counterpart`, {
    method: 'POST', headers: { origin, 'content-type': 'application/json' },
    body: JSON.stringify({ token: grant.token, peer_id: grant.peer_id, ...extra }),
  });
  assert.equal((await discover(patient)).status, 403); // Unconsumed is not online.
  const malformed = await fetch(`${api.base}/peerjs/counterpart`, {
    method: 'POST', headers: { origin: 'https://localhost:8443', 'content-type': 'application/json' },
    body: `{"token":"${patient.token}",`,
  });
  assert.equal(malformed.status, 400);
  assert.equal(malformed.headers.get('cache-control'), 'no-store');
  assert.equal((await malformed.text()).includes(patient.token), false);
  await api.connect(patient);
  assert.deepEqual(await (await discover(patient)).json(), { peer_id: null });
  const foreign = api.issue('doctor-b', 'b');
  await api.connect(foreign);
  assert.deepEqual(await (await discover(patient)).json(), { peer_id: null });
  assert.equal((await discover(patient, 'https://evil.test')).status, 403);
  assert.equal((await discover(patient, undefined, { appointment_id: 'b' })).status, 403);
  assert.equal((await discover({ ...patient, token: doctor.token })).status, 403);
  const wire = await api.connect(doctor);
  assert.deepEqual(await (await discover(patient)).json(), { peer_id: doctor.peer_id });
  assert.deepEqual(await (await discover(doctor)).json(), { peer_id: patient.peer_id });
  await close(wire);
  await released(api, doctor);
  assert.deepEqual(await (await discover(patient)).json(), { peer_id: null });
  const fresh = api.issue('doctor-a');
  await api.connect(fresh);
  assert.deepEqual(await (await discover(patient)).json(), { peer_id: fresh.peer_id });
  assert.equal((await discover(doctor)).status, 403);
  api.state.revoked = true;
  assert.equal((await discover(patient)).status, 403);
});

test('same-appointment frames pass; cross-appointment, forged and malformed frames close before routing', async (t) => {
  const api = await setup(t);
  const target = api.issue('doctor-a');
  const receiver = await api.connect(target);
  for (const type of ['OFFER', 'ANSWER', 'CANDIDATE', 'LEAVE', 'EXPIRE']) {
    const grant = api.issue();
    const caller = await api.connect(grant);
    const received = once(receiver, 'message');
    caller.send(JSON.stringify({ type, dst: target.peer_id, payload: { type } }));
    assert.equal(JSON.parse((await received)[0]).src, grant.peer_id);
    await close(caller);
    await released(api, grant);
  }
  const foreign = api.issue('patient-b', 'b');
  const foreignWire = await api.connect(foreign);
  const callerGrant = api.issue();
  const caller = await api.connect(callerGrant);
  let leaked = false;
  foreignWire.on('message', () => { leaked = true; });
  const ended = once(caller, 'close');
  caller.send(JSON.stringify({ type: 'OFFER', dst: foreign.peer_id }));
  assert.equal((await ended)[0], 1008);
  assert.equal(leaked, false);
  await released(api, callerGrant);
  for (const frame of ['null', '[]', '{bad', JSON.stringify({ type: 'HEARTBEAT', src: 'forged' }),
    JSON.stringify({ type: 'OFFER', dst: randomUUID() }), JSON.stringify({ type: 'UNKNOWN' }),
    Buffer.from('{"type":"HEARTBEAT"}')]) {
    const grant = api.issue();
    const wire = await api.connect(grant);
    const closed = once(wire, 'close'); wire.send(frame);
    assert.equal((await closed)[0], 1008);
    await released(api, grant);
  }
});

test('disconnect releases the participant; rejoin uses a fresh peer and credential', async (t) => {
  const api = await setup(t);
  const first = api.issue();
  await close(await api.connect(first));
  for (let i = 0; i < 40 && !api.state.releases; i++) await delay(10);
  assert.ok(api.state.releases);
  const fresh = api.issue();
  assert.notEqual(first.peer_id, fresh.peer_id);
  await close(await api.connect(fresh));
});

test('expiry closes idle sockets; a consumed lease is never extended', async (t) => {
  const api = await setup(t, { ttlMs: 250 });
  const wire = await api.connect(api.issue());
  assert.equal((await once(wire, 'close'))[0], 1008);
});

test('service revocation and outages close idle sockets and reject new registrations', async (t) => {
  for (const flag of ['revoked', 'unavailable']) {
    await t.test(flag, async (t) => {
      const api = await setup(t);
      const wire = await api.connect(api.issue());
      const closed = once(wire, 'close');
      api.state[flag] = true;
      assert.equal((await closed)[0], 1008);
      await assert.rejects(api.connect(api.issue('doctor-a')), /403/);
    });
  }
});

test('draining closes admitted clients and stops new admission', async (t) => {
  const api = await setup(t);
  const wire = await api.connect(api.issue());
  const closed = once(wire, 'close'); api.server.drain();
  assert.equal((await closed)[0], 1008);
  assert.equal((await fetch(`${api.base}/healthz`)).status, 503);
  await assert.rejects(api.connect(api.issue()), /403/);
});
