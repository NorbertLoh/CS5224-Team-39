import test from 'node:test';
import assert from 'node:assert/strict';
import { createHmac } from 'node:crypto';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { turnCredentials } from '../credentials.mjs';
import { createSpikeServer } from '../server.mjs';

test('TURN REST credentials match timestamp:HMAC-SHA1 and expire', () => {
  const secret = 'test-only-secret-that-is-at-least-32-characters';
  const result = turnCredentials(secret, 'tester-a', 600, 1700000000000);
  assert.equal(result.username, '1700000600:tester-a');
  assert.equal(result.expiresAt, '2023-11-14T22:23:20.000Z');
  assert.equal(result.credential, createHmac('sha1', secret).update(result.username).digest('base64'));
  assert.throws(() => turnCredentials('short'));
  assert.throws(() => turnCredentials(secret, 'personal:identifier'));
  assert.throws(() => turnCredentials(secret, 'a', 3601));
  assert.throws(() => turnCredentials(secret, 'a', 0));
});

test('non-loopback HTTP and incomplete TLS fail before binding', () => {
  assert.throws(() => createSpikeServer({ SPIKE_HOST: '0.0.0.0' }), /requires TLS/);
  assert.throws(() => createSpikeServer({ SPIKE_TLS_KEY: 'missing' }), /Set both/);
  assert.throws(() => createSpikeServer({ SPIKE_PORT: 'NaN' }), /Invalid/);
});

test('self-hosted assets and PeerServer ID route work; discovery stays disabled', async () => {
  // PeerServer owns recurring timers without a public shutdown API: isolate its process.
  const child = spawn(process.execPath, ['server.mjs'], {
    cwd: new URL('..', import.meta.url),
    env: { ...process.env, SPIKE_PORT: '0', SPIKE_HOST: '127.0.0.1', SPIKE_TLS_CERT: '', SPIKE_TLS_KEY: '' },
    stdio: ['ignore', 'pipe', 'inherit'],
  });
  try {
    const base = await new Promise((resolve, reject) => {
      const timeout = setTimeout(() => reject(new Error('Spike did not start')), 10000);
      child.once('error', reject);
      child.stdout.on('data', (chunk) => {
        const match = chunk.toString().match(/http:\/\/127\.0\.0\.1:\d+/);
        if (match) { clearTimeout(timeout); resolve(match[0]); }
      });
    });
    const health = await fetch(`${base}/healthz`);
    assert.deepEqual(await health.json(), { status: 'ok', spike: 'X01' });
    for (const path of ['/', '/app.js', '/style.css', '/vendor/peerjs.min.js']) {
      const response = await fetch(base + path);
      assert.equal(response.status, 200, path);
      assert.equal(response.headers.get('cache-control'), 'no-store');
      assert.ok(response.headers.get('content-security-policy').includes("connect-src 'self'"));
      await response.arrayBuffer();
    }
    const id = await fetch(`${base}/peerjs/x01/id`);
    assert.equal(id.status, 200);
    assert.match(await id.text(), /^[a-zA-Z0-9-]+$/);
    const discovery = await fetch(`${base}/peerjs/x01/peers`);
    assert.equal(discovery.status, 401);
    await discovery.arrayBuffer();
    const privateFile = await fetch(`${base}/credentials.mjs`);
    assert.equal(privateFile.status, 404);
    await privateFile.arrayBuffer();
  } finally {
    const stopped = once(child, 'exit');
    child.kill();
    await stopped;
  }
});
