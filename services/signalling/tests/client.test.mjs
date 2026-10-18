import test from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import { once } from 'node:events';
import { randomUUID } from 'node:crypto';
import { Admissions } from '../src/admissions.mjs';
import { SECRET } from './fixtures.mjs';

test('admission client rejects malformed, redirected, oversized and changed lease responses', async (t) => {
  const peerId = randomUUID();
  const token = 'a'.repeat(43);
  const valid = { peer_id: peerId, subject_id: randomUUID(), appointment_id: randomUUID(),
    tenant_id: randomUUID(), session_id: randomUUID(), expires_at: new Date(Date.now() + 60000).toISOString() };
  let mode = 'valid';
  const server = http.createServer((_request, response) => {
    if (mode === 'redirect') { response.writeHead(302, { location: 'http://127.0.0.1/elsewhere' }); response.end(); return; }
    response.setHeader('content-type', 'application/json');
    const body = { invalid: '{}', oversized: ' '.repeat(5000), wrongPeer: JSON.stringify({ ...valid, peer_id: randomUUID() }),
      expired: JSON.stringify({ ...valid, expires_at: new Date(Date.now() - 1000).toISOString() }),
      changed: JSON.stringify({ ...valid, tenant_id: randomUUID() }) }[mode] || JSON.stringify(valid);
    response.end(body);
  });
  server.listen(0, '127.0.0.1'); await once(server, 'listening');
  t.after(() => { server.closeAllConnections(); server.close(); });
  const client = new Admissions({ url: `http://127.0.0.1:${server.address().port}`, secret: SECRET, timeoutMs: 100 });
  const grant = await client.consume(token, peerId);
  for (mode of ['invalid', 'oversized', 'wrongPeer', 'expired', 'redirect']) {
    await assert.rejects(client.consume(token, peerId));
  }
  mode = 'changed';
  await assert.rejects(client.check(grant));
});

test('upstream timeout is bounded and never retries consumption', async (t) => {
  let requests = 0;
  const server = http.createServer(() => { requests++; });
  server.listen(0, '127.0.0.1'); await once(server, 'listening');
  t.after(() => { server.closeAllConnections(); server.close(); });
  const client = new Admissions({ url: `http://127.0.0.1:${server.address().port}`, secret: SECRET, timeoutMs: 30 });
  await assert.rejects(client.consume('a'.repeat(43), randomUUID()));
  assert.equal(requests, 1);
});
