import assert from 'node:assert/strict';
import { once } from 'node:events';
import { mkdtempSync, writeFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import test from 'node:test';
import { callbackServer, CALLBACK_PATH, identifier, loadConfig, orderSummary, quoteSummary,
  request, signature, verifyCallback } from './lalamove-spike.mjs';

const config = { LALAMOVE_API_KEY: 'pk_test_example', LALAMOVE_API_SECRET: 'sk_test_example/=',
  LALAMOVE_MARKET: 'SG', LALAMOVE_BASE_URL: 'https://rest.sandbox.lalamove.com' };
const now = Date.now();
function event() {
  const value = { apiKey: config.LALAMOVE_API_KEY, timestamp: Math.floor(now / 1000),
    eventType: 'ORDER_STATUS_CHANGED', data: { order: { orderId: '1234567890123456789', status: 'ON_GOING' },
      unicode: '测试', optional: null, nested: [true, 1, 'é'] } };
  value.signature = signature(config.LALAMOVE_API_SECRET, value.timestamp, 'POST', CALLBACK_PATH,
    JSON.stringify(value.data));
  return value;
}
function quote() {
  return { quotationId: '1234567890123456789', serviceType: 'MOTORCYCLE',
    priceBreakdown: { total: '7.8', currency: 'SGD' },
    expiresAt: new Date(now + 300000).toISOString(),
    stops: [{ stopId: '1234567890123456790' }, { stopId: '1234567890123456791' }] };
}

test('HMAC matches independently computed Python reference vector', () => {
  assert.equal(signature('sk_test_reference', 1625220901, 'POST', CALLBACK_PATH,
    '{"status":"ON_GOING"}'), '1c01afd8fa5c621050a9ab4406dd985a10575461fb811bd266415196ab236343');
});

test('request signs exactly the transmitted JSON and refuses redirects', async () => {
  await request(config, 'POST', '/v3/quotations', { label: '测试' }, async (url, options) => {
    assert.equal(url, 'https://rest.sandbox.lalamove.com/v3/quotations');
    assert.equal(options.redirect, 'error');
    const [key, stamp, actual] = options.headers.Authorization.slice(5).split(':');
    assert.equal(key, config.LALAMOVE_API_KEY);
    assert.equal(actual, signature(config.LALAMOVE_API_SECRET, stamp, 'POST', '/v3/quotations', options.body));
    return { ok: true, status: 201, json: async () => ({ data: {} }) };
  });
});

test('config permits sandbox secret alphabet, rejects live keys/hosts/markets', () => {
  const folder = mkdtempSync(join(tmpdir(), 'x05-'));
  try {
    const path = join(folder, '.env');
    for (const changes of [{}, { LALAMOVE_API_KEY: 'pk_prod_example' },
      { LALAMOVE_API_SECRET: 'sk_prod_example' }, { LALAMOVE_BASE_URL: 'https://rest.lalamove.com' },
      { LALAMOVE_MARKET: 'HK' }]) {
      writeFileSync(path, Object.entries({ ...config, ...changes }).map(([k, v]) => `${k}=${v}`).join('\n'));
      if (Object.keys(changes).length) assert.throws(() => loadConfig(path));
      else assert.deepEqual(loadConfig(path), config);
    }
  } finally { rmSync(folder, { recursive: true }); }
});

test('provider errors omit raw responses and do not retry order creation', async () => {
  let count = 0;
  await assert.rejects(request(config, 'POST', '/v3/orders', {}, async () => {
    count++;
    return { ok: false, status: 402, json: () => { throw new Error('must not read'); } };
  }), /Lalamove HTTP 402/);
  assert.equal(count, 1);
  await assert.rejects(request(config, 'GET', '/v3/orders/../secrets'), /Unsupported API path/);
});

test('IDs retain precision and reject URL injection', () => {
  assert.equal(identifier('3608770529626608275'), '3608770529626608275');
  for (const bad of [3608770529626608275, '../abc', '123?secret=x', '', null]) {
    assert.throws(() => identifier(bad));
  }
});

test('quote validates SGD minor units and unexpired linked stop IDs', () => {
  assert.equal(quoteSummary(quote(), now).amount_minor, 780);
  for (const change of [{ expiresAt: new Date(now).toISOString() }, { expiresAt: 'bad' },
    { priceBreakdown: { total: 'NaN', currency: 'SGD' } },
    { priceBreakdown: { total: '1.001', currency: 'SGD' } },
    { priceBreakdown: { total: '7.8', currency: 'USD' } }, { stops: [] }]) {
    assert.throws(() => quoteSummary({ ...quote(), ...change }, now));
  }
});

test('order status must be known and linked to X05 quotation', () => {
  const order = { orderId: '1234567890123456789', quotationId: '2234567890123456789',
    status: 'ASSIGNING_DRIVER', metadata: { task: 'X05' }, priceBreakdown: { currency: 'SGD', total: '7.8' } };
  assert.equal(orderSummary(order, order.quotationId).status, 'ASSIGNING_DRIVER');
  assert.throws(() => orderSummary(order, '3234567890123456789'));
  assert.throws(() => orderSummary({ ...order, metadata: {} }));
  assert.throws(() => orderSummary({ ...order, status: 'INVENTED' }));
});

test('provider callback JSON.stringify convention verifies nested Unicode data', () => {
  assert.equal(verifyCallback(event(), config, CALLBACK_PATH, now).authenticated, true);
  // Whitespace outside parsed data is not part of Lalamove's documented signature.
  assert.equal(verifyCallback(JSON.parse(JSON.stringify(event(), null, 2)), config, CALLBACK_PATH, now).authenticated, true);
});

test('callback rejects wrong key, changed data, secret, path, timestamp and malformed signatures', () => {
  for (const change of [{ apiKey: 'pk_test_other' }, { signature: 'bad' },
    { signature: 'a'.repeat(64) }, { data: { order: { status: 'COMPLETED' } } },
    { timestamp: Math.floor(now / 1000) - 86401 }, { timestamp: Math.floor(now / 1000) + 301 },
    { timestamp: String(Math.floor(now / 1000)) }, { data: null }]) {
    assert.throws(() => verifyCallback({ ...event(), ...change }, config, CALLBACK_PATH, now));
  }
  assert.throws(() => verifyCallback(event(), { ...config, LALAMOVE_API_SECRET: 'sk_test_other' }));
  assert.throws(() => verifyCallback(event(), config, '/wrong'));
});

test('actual HTTP callback: probe, valid event, replay, forgery and size/path limits', async () => {
  const events = [];
  const server = callbackServer(config, value => events.push(value));
  server.listen(0, '127.0.0.1');
  await once(server, 'listening');
  const url = `http://127.0.0.1:${server.address().port}`;
  const post = (body, path = CALLBACK_PATH) => fetch(url + path, { method: 'POST', body });
  try {
    assert.equal((await post('')).status, 200);
    assert.equal(events.length, 0);
    assert.equal((await post(JSON.stringify(event()))).status, 200);
    assert.equal((await post(JSON.stringify(event()))).status, 200);
    assert.equal(events.length, 1);
    assert.equal((await post(JSON.stringify({ ...event(), signature: 'bad' }))).status, 400);
    assert.equal((await post('{bad')).status, 400);
    assert.equal((await post('x'.repeat(65537))).status, 413);
    assert.equal((await post('', '/other')).status, 404);
    assert.equal((await fetch(url + CALLBACK_PATH)).status, 404);
  } finally { server.closeAllConnections(); await new Promise(resolve => server.close(resolve)); }
});
