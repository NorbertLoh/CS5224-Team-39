import express from 'express';
import { ExpressPeerServer } from 'peer';
import http from 'node:http';
import https from 'node:https';
import { readFileSync } from 'node:fs';
import { fileURLToPath, pathToFileURL } from 'node:url';

export function createSpikeServer(env = process.env) {
  const host = env.SPIKE_HOST || '127.0.0.1';
  const port = Number(env.SPIKE_PORT || 9000);
  if (!Number.isInteger(port) || port < 0 || port > 65535) throw new Error('Invalid SPIKE_PORT');
  const tls = Boolean(env.SPIKE_TLS_CERT && env.SPIKE_TLS_KEY);
  if (Boolean(env.SPIKE_TLS_CERT) !== Boolean(env.SPIKE_TLS_KEY)) {
    throw new Error('Set both SPIKE_TLS_CERT and SPIKE_TLS_KEY');
  }
  if (!tls && !['127.0.0.1', '::1', 'localhost'].includes(host)) {
    throw new Error('Non-loopback binding requires TLS');
  }
  const app = express();
  app.disable('x-powered-by');
  app.use((_req, res, next) => {
    res.set({
      'Cache-Control': 'no-store',
      'X-Content-Type-Options': 'nosniff',
      'Referrer-Policy': 'no-referrer',
      'Permissions-Policy': 'camera=(self), microphone=(self)',
      'Content-Security-Policy': "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; media-src 'self' blob:; object-src 'none'; frame-ancestors 'none'",
    });
    next();
  });
  const server = tls
    ? https.createServer({ cert: readFileSync(env.SPIKE_TLS_CERT), key: readFileSync(env.SPIKE_TLS_KEY) }, app)
    : http.createServer(app);
  app.get('/healthz', (_req, res) => res.json({ status: 'ok', spike: 'X01' }));
  app.get('/vendor/peerjs.min.js', (_req, res) => {
    res.sendFile(fileURLToPath(new URL('./node_modules/peerjs/dist/peerjs.min.js', import.meta.url)), { dotfiles: 'allow' });
  });
  app.use('/peerjs', ExpressPeerServer(server, {
    path: '/', key: 'x01', allow_discovery: false, concurrent_limit: 10,
  }));
  app.use(express.static(fileURLToPath(new URL('./public', import.meta.url))));
  return { server, host, port, tls };
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const { server, host, port, tls } = createSpikeServer();
  server.listen(port, host, () => {
    console.log(`X01 spike: ${tls ? 'https' : 'http'}://${host}:${server.address().port}`);
  });
  for (const signal of ['SIGINT', 'SIGTERM']) process.on(signal, () => {
    server.close();
    server.closeAllConnections();
    // PeerServer owns upgraded WebSockets, so bound shutdown rather than waiting for them.
    setTimeout(() => process.exit(0), 500).unref();
  });
}
