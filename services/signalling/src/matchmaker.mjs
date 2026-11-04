import { randomBytes, randomUUID } from 'node:crypto';
import http from 'node:http';
import { isIP } from 'node:net';
import { serviceToken, validCredential } from './admissions.mjs';

export const nodePattern = '[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}';
const socketPath = new RegExp(`^/peerjs/nodes/(${nodePattern})/peerjs$`);

function internalEndpoint(value) {
  const url = new URL(value);
  if (url.protocol !== 'http:' || isIP(url.hostname) !== 4
    || url.username || url.password || url.search || url.hash || url.pathname !== '/') {
    throw new Error('Invalid node endpoint');
  }
  return url;
}

export class Matchmaker {
  constructor(config) {
    this.config = config;
    config.nodeId ||= randomUUID();
    config.nodeToken ||= randomBytes(32).toString('base64url');
    this.draining = false;
    this.expiresAt = 0;
    this.proxies = new Set();
    this.pending = 0;
  }

  async request(path, options = {}) {
    const response = await fetch(`${this.config.url}/internal/signalling${path}`, {
      ...options, redirect: 'error', signal: AbortSignal.timeout(this.config.timeoutMs),
      headers: { authorization: `Bearer ${serviceToken(this.config.secret)}`, 'content-type': 'application/json' },
    });
    if (!response.ok) { await response.body?.cancel(); throw new Error('Signalling unavailable'); }
    const body = await response.text();
    if (body.length > 1024) throw new Error('Invalid registry response');
    return JSON.parse(body);
  }

  async heartbeat() {
    const sentAt = Date.now();
    const result = await this.request('/heartbeat', { method: 'POST', body: JSON.stringify({
      node_id: this.config.nodeId, node_token: this.config.nodeToken,
      internal_url: this.config.internalUrl, draining: this.draining,
    }) });
    // Use duration relative to request start: DB and task clocks may differ.
    // The backend returns a bounded lease; retain a conservative local deadline.
    if (typeof result.lease_expires_at !== 'string' || !Number.isFinite(Date.parse(result.lease_expires_at))) {
      throw new Error('Invalid heartbeat');
    }
    if (!Number.isInteger(result.lease_seconds) || result.lease_seconds < 10 || result.lease_seconds > 120) {
      throw new Error('Invalid heartbeat duration');
    }
    this.expiresAt = Math.max(this.expiresAt, sentAt + result.lease_seconds * 1000);
  }

  live() { return Date.now() < this.expiresAt; }

  async resolve(nodeId) {
    const result = await this.request(`/nodes/${nodeId}`);
    return internalEndpoint(result.internal_url);
  }

  async counterpart(nodeId, body, origin) {
    if (!this.config.origins.includes(origin) || this.pending >= this.config.maxConnections) {
      throw new Error('Routing denied');
    }
    this.pending++;
    try {
      const url = await this.resolve(nodeId);
      const response = await fetch(new URL(`/peerjs/nodes/${nodeId}/counterpart`, url), {
        method: 'POST', body: JSON.stringify(body), redirect: 'error',
        headers: { origin, 'content-type': 'application/json', 'x-telelink-proxy-hop': '1' },
        signal: AbortSignal.timeout(this.config.timeoutMs),
      });
      if (!response.ok) { await response.body?.cancel(); throw new Error('Discovery denied'); }
      const text = await response.text();
      if (text.length > 1024) throw new Error('Invalid discovery');
      return JSON.parse(text);
    } finally { this.pending--; }
  }

  async upgrade(request, socket, head) {
    const url = new URL(request.url, 'http://localhost');
    const match = socketPath.exec(url.pathname);
    if (!match || !this.live() || request.method !== 'GET'
      || !this.config.origins.includes(request.headers.origin)) throw new Error('Routing denied');
    const query = url.searchParams;
    if (query.get('key') !== this.config.key || !validCredential(query.get('token'), query.get('id'))) {
      throw new Error('Routing denied');
    }
    const nodeId = match[1];
    if (nodeId === this.config.nodeId) {
      request.url = `/peerjs/peerjs${url.search}`;
      return false;
    }
    if (request.headers['x-telelink-proxy-hop'] || this.pending + this.proxies.size >= this.config.maxConnections) {
      throw new Error('Routing denied');
    }
    this.pending++;
    try {
      const target = await this.resolve(nodeId);
      if (socket.destroyed) return true;
      await this.relay(new URL(`${url.pathname}${url.search}`, target), request, socket, head);
      return true;
    } finally { this.pending--; }
  }

  relay(target, request, socket, head) {
    return new Promise((done) => {
      const upstream = http.request(target, { method: 'GET', headers: {
        connection: 'Upgrade', upgrade: 'websocket', origin: request.headers.origin,
        'sec-websocket-key': request.headers['sec-websocket-key'],
        'sec-websocket-version': request.headers['sec-websocket-version'],
        'x-telelink-proxy-hop': '1',
      } });
      const finish = () => { clearTimeout(timeout); upstream.destroy(); done(); };
      const fail = () => { finish(); socket.destroy(); };
      const timeout = setTimeout(fail, this.config.timeoutMs * 2);
      socket.once('close', finish);
      socket.once('error', fail);
      upstream.once('error', fail);
      upstream.once('response', () => {
        finish();
        socket.end('HTTP/1.1 403 Forbidden\r\nConnection: close\r\nContent-Length: 0\r\n\r\n');
      });
      upstream.once('upgrade', async (response, remote, remoteHead) => {
        socket.once('close', () => remote.destroy());
        remote.once('error', fail);
        remote.once('close', fail);
        try {
          await this.config.protection?.ensure();
          if (socket.destroyed || remote.destroyed || response.statusCode !== 101) {
            remote.destroy(); fail(); return;
          }
          clearTimeout(timeout);
          this.proxies.add(socket);
          socket.once('close', () => this.proxies.delete(socket));
          socket.write('HTTP/1.1 101 Switching Protocols\r\n' +
            ['upgrade', 'connection', 'sec-websocket-accept'].map((key) => `${key}: ${response.headers[key]}\r\n`).join('') + '\r\n');
          if (remoteHead.length) socket.write(remoteHead);
          if (head.length) remote.write(head);
          socket.pipe(remote).pipe(socket);
          socket.resume();
          done();
        } catch { remote.destroy(); fail(); }
      });
      upstream.end();
    });
  }

  close() { for (const socket of this.proxies) socket.destroy(); }
}

export async function discoverInternalUrl(config, env = process.env) {
  if (config.internalUrl) return internalEndpoint(config.internalUrl).origin;
  // ECS v4 metadata URI is injected by the runtime, never supplied by browsers.
  const metadata = env.ECS_CONTAINER_METADATA_URI_V4;
  if (!metadata?.startsWith('http://169.254.170.2/')) throw new Error('Node address required');
  const response = await fetch(metadata, { redirect: 'error', signal: AbortSignal.timeout(2000) });
  if (!response.ok) throw new Error('Node metadata unavailable');
  const data = await response.json();
  const address = data.Networks?.flatMap((network) => network.IPv4Addresses || [])[0];
  if (isIP(address) !== 4) throw new Error('Invalid node address');
  return `http://${address}:${config.port}`;
}
