/** X05: isolated SG sandbox tooling; never updates application delivery state. */
import { createHmac, randomUUID, timingSafeEqual } from 'node:crypto';
import { readFileSync, appendFileSync } from 'node:fs';
import { createServer } from 'node:http';
import { fileURLToPath } from 'node:url';

const HOST = 'https://rest.sandbox.lalamove.com';
const ENV = new URL('../.env', import.meta.url);
export const CALLBACK_PATH = '/x05/lalamove';
const STATUSES = new Set(['ASSIGNING_DRIVER', 'ON_GOING', 'PICKED_UP', 'COMPLETED',
  'CANCELED', 'REJECTED', 'EXPIRED']);

function requireThat(value, message) {
  if (!value) throw new Error(message);
}

export function loadConfig(path = ENV) {
  const names = ['LALAMOVE_API_KEY', 'LALAMOVE_API_SECRET', 'LALAMOVE_MARKET',
    'LALAMOVE_BASE_URL'];
  const config = {};
  for (const line of readFileSync(path, 'utf8').replace(/^\uFEFF/, '').split(/\r?\n/)) {
    const match = line.match(/^([A-Z_]+)=(.*)$/);
    if (match && names.includes(match[1])) config[match[1]] = match[2].trim().replace(/^(['"])(.*)\1$/, '$2');
  }
  for (const name of names) if (process.env[name] !== undefined) config[name] = process.env[name];
  requireThat(/^pk_test[\w-]+$/.test(config.LALAMOVE_API_KEY ?? ''), 'Sandbox API key required');
  requireThat(/^sk_test[\w+/=-]+$/.test(config.LALAMOVE_API_SECRET ?? ''), 'Sandbox secret required');
  requireThat(config.LALAMOVE_MARKET === 'SG', 'Only SG sandbox supported');
  requireThat(config.LALAMOVE_BASE_URL === HOST, 'Only the fixed sandbox host is supported');
  return config;
}

export function signature(secret, timestamp, method, path, body = '') {
  return createHmac('sha256', secret)
    .update(`${timestamp}\r\n${method}\r\n${path}\r\n\r\n${body}`, 'utf8').digest('hex');
}

export async function request(config, method, path, data, transport = fetch) {
  requireThat(/^\/v3\/(cities|quotations(?:\/\d+)?|orders(?:\/\d+)?|webhook)$/.test(path), 'Unsupported API path');
  const body = data === undefined ? '' : JSON.stringify({ data });
  const timestamp = Date.now().toString();
  const response = await transport(HOST + path, {
    method, redirect: 'error', signal: AbortSignal.timeout(30000),
    headers: { 'Content-Type': 'application/json', Market: 'SG', 'Request-ID': randomUUID(),
      Authorization: `hmac ${config.LALAMOVE_API_KEY}:${timestamp}:${signature(config.LALAMOVE_API_SECRET, timestamp, method, path, body)}` },
    ...(body ? { body } : {}),
  });
  if (!response.ok) throw new Error(`Lalamove HTTP ${response.status}; inspect sandbox logs (raw response omitted)`);
  return response.status === 204 ? null : (await response.json()).data;
}

export function identifier(value) {
  requireThat(typeof value === 'string' && /^\d{10,30}$/.test(value), 'Invalid provider identifier');
  return value;
}

export function quoteSummary(quote, now = Date.now()) {
  const price = quote?.priceBreakdown;
  requireThat(price?.currency === 'SGD' && typeof price.total === 'string'
    && /^\d+(?:\.\d{1,2})?$/.test(price.total), 'Invalid SGD quotation price');
  const [whole, decimal = ''] = price.total.split('.');
  const minor = Number(whole) * 100 + Number(decimal.padEnd(2, '0'));
  requireThat(Number.isSafeInteger(minor), 'Price outside supported range');
  requireThat(Number.isFinite(Date.parse(quote.expiresAt)) && Date.parse(quote.expiresAt) > now,
    'Quotation expired or expiry missing');
  requireThat(quote.serviceType === 'MOTORCYCLE' && quote.stops?.length === 2,
    'Expected two-stop motorcycle quotation');
  return { quotation_id: identifier(quote.quotationId), currency: 'SGD', amount_minor: minor,
    expires_at: quote.expiresAt, service_type: quote.serviceType,
    stop_ids: quote.stops.map(stop => identifier(stop.stopId)) };
}

export function orderSummary(order, expectedQuote) {
  requireThat(STATUSES.has(order?.status), 'Unknown order status');
  requireThat(order.metadata?.task === 'X05', 'Not an X05 sandbox order');
  if (expectedQuote) requireThat(order.quotationId === expectedQuote, 'Order quotation mismatch');
  requireThat(order.priceBreakdown?.currency === 'SGD'
    && typeof order.priceBreakdown.total === 'string'
    && /^\d+(?:\.\d{1,2})?$/.test(order.priceBreakdown.total), 'Invalid SGD order price');
  return { order_id: identifier(order.orderId), quotation_id: identifier(order.quotationId),
    status: order.status, currency: 'SGD', total: order.priceBreakdown.total };
}

export function quotePayload() {
  return { serviceType: 'MOTORCYCLE', language: 'en_SG', stops: [
    { coordinates: { lat: '1.2844', lng: '103.8511' }, address: '1 Raffles Place, Singapore 048616' },
    { coordinates: { lat: '1.2935', lng: '103.8572' }, address: '3 Temasek Boulevard, Singapore 038983' },
  ] };
}

export function verifyCallback(event, config, path = CALLBACK_PATH, now = Date.now()) {
  requireThat(event && event.apiKey === config.LALAMOVE_API_KEY, 'Wrong callback API key');
  requireThat(Number.isSafeInteger(event.timestamp), 'Invalid callback timestamp');
  // The provider example uses seconds. Allow its documented retry window, not arbitrary old events.
  requireThat(event.timestamp * 1000 >= now - 86400000 && event.timestamp * 1000 <= now + 300000,
    'Callback timestamp outside retry window');
  requireThat(event.data && typeof event.data === 'object' && !Array.isArray(event.data), 'Missing callback data');
  const expected = signature(config.LALAMOVE_API_SECRET, event.timestamp, 'POST', path, JSON.stringify(event.data));
  requireThat(typeof event.signature === 'string' && /^[a-f0-9]{64}$/.test(event.signature)
    && timingSafeEqual(Buffer.from(event.signature, 'hex'), Buffer.from(expected, 'hex')), 'Invalid callback signature');
  // eventType/eventId are outside the signed data; never use them as application truth.
  return { authenticated: true, signature: event.signature,
    order_id: event.data.order?.orderId ?? event.data.order?.id ?? null,
    status: event.data.order?.status ?? null };
}

export function callbackServer(config, onVerified = () => {}) {
  const seen = new Map();
  return createServer(async (req, res) => {
    const reply = (code) => { res.writeHead(code); res.end(); };
    if (req.url !== CALLBACK_PATH || req.method !== 'POST') return reply(404);
    try {
      let size = 0;
      const parts = [];
      for await (const part of req) {
        size += part.length;
        if (size > 65536) return reply(413);
        parts.push(part);
      }
      const raw = Buffer.concat(parts).toString('utf8');
      // Provider's empty-body registration probe is acknowledged without authenticating an event.
      if (!raw) return reply(200);
      const result = verifyCallback(JSON.parse(raw), config);
      const now = Date.now();
      for (const [key, expiry] of seen) if (expiry < now) seen.delete(key);
      if (!seen.has(result.signature)) {
        requireThat(seen.size < 10000, 'Spike callback capacity reached');
        onVerified({ authenticated: true, order_id: result.order_id, status: result.status });
        seen.set(result.signature, now + 86400000);
      }
      reply(200);
    } catch { reply(400); }
  });
}

async function main() {
  const [command, value] = process.argv.slice(2);
  const config = loadConfig();
  let result;
  if (command === 'cities') {
    const cities = await request(config, 'GET', '/v3/cities');
    result = { mode: 'lalamove-sandbox', cities: cities.map(c => ({ name: c.name,
      services: c.services.map(s => s.key) })) };
  } else if (command === 'quote') {
    const created = await request(config, 'POST', '/v3/quotations', quotePayload());
    const fetched = await request(config, 'GET', `/v3/quotations/${identifier(created.quotationId)}`);
    requireThat(created.quotationId === fetched.quotationId, 'Quotation retrieval mismatch');
    result = { mode: 'lalamove-sandbox', ...quoteSummary(fetched) };
  } else if (command === 'create') {
    const quote = await request(config, 'GET', `/v3/quotations/${identifier(value)}`);
    const summary = quoteSummary(quote);
    const order = await request(config, 'POST', '/v3/orders', {
      quotationId: summary.quotation_id,
      sender: { stopId: summary.stop_ids[0], name: 'X05 synthetic sender', phone: '+6580000000' },
      recipients: [{ stopId: summary.stop_ids[1], name: 'X05 synthetic recipient', phone: '+6580000001' }],
      metadata: { task: 'X05' }, isPODEnabled: false,
    });
    // Never automatically retry POST orders: Request-ID is not documented as an idempotency key.
    console.log(JSON.stringify({ created_order_id: identifier(order.orderId) }));
    const fetched = await request(config, 'GET', `/v3/orders/${identifier(order.orderId)}`);
    requireThat(fetched.orderId === order.orderId, 'Order retrieval mismatch');
    result = { mode: 'lalamove-sandbox', ...orderSummary(fetched, summary.quotation_id) };
  } else if (command === 'status' || command === 'cancel') {
    const path = `/v3/orders/${identifier(value)}`;
    const order = await request(config, 'GET', path);
    orderSummary(order);
    if (command === 'cancel') await request(config, 'DELETE', path);
    result = { mode: 'lalamove-sandbox', ...orderSummary(await request(config, 'GET', path)) };
  } else if (command === 'clear-webhook') {
    await request(config, 'PATCH', '/v3/webhook', { url: '' });
    result = { webhook_cleared: true };
  } else if (command === 'webhook') {
    const url = new URL(value);
    requireThat(url.protocol === 'https:' && !url.username && !url.password
      && url.pathname === CALLBACK_PATH && !url.search && !url.hash, 'Expected HTTPS callback URL ending in ' + CALLBACK_PATH);
    await request(config, 'PATCH', '/v3/webhook', { url: url.href });
    result = { webhook_registered: true };
  } else if (command === 'listen') {
    const server = callbackServer(config, evidence => {
      const line = JSON.stringify({ received_at: new Date().toISOString(), ...evidence });
      if (value) appendFileSync(value, line + '\n');
      console.log(line);
    });
    server.requestTimeout = 10000;
    server.listen(8017, '127.0.0.1', () => console.log('X05 callback listening on 127.0.0.1:8017'));
    return;
  } else throw new Error('Commands: cities | quote | create QUOTE_ID | status ORDER_ID | cancel ORDER_ID | webhook HTTPS_URL | clear-webhook | listen [EVIDENCE_FILE]');
  console.log(JSON.stringify(result, null, 2));
}

if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) {
  main().catch(error => {
    console.error(error.message.startsWith('Lalamove HTTP') ? error.message
      : ['fetch failed', 'Unexpected token'].some(s => error.message.includes(s))
        ? 'Provider transport/JSON failure; raw data omitted' : error.message);
    process.exitCode = 1;
  });
}
