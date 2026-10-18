import express from 'express';
import http from 'node:http';
import { pathToFileURL } from 'node:url';
import { ExpressPeerServer } from 'peer';
import { Admissions } from './admissions.mjs';
import { configuration } from './config.mjs';
import { admissionTransport } from './transport.mjs';

export function createServer(config, admissions = new Admissions(config)) {
  const app = express();
  const server = http.createServer({ requestTimeout: 10000, headersTimeout: 10000 }, app);
  let transport;
  let draining = false;
  app.disable('x-powered-by');
  app.use((_request, response, next) => {
    response.set({ 'Cache-Control': 'no-store', 'Referrer-Policy': 'no-referrer',
      'X-Content-Type-Options': 'nosniff' });
    next();
  });
  app.get('/healthz', (_request, response) => response.status(draining ? 503 : 200)
    .json({ status: draining ? 'draining' : 'ok', service: 'signalling' }));
  const peer = ExpressPeerServer(server, {
    path: '/', key: config.key, allow_discovery: false, concurrent_limit: config.maxConnections,
    createWebSocketServer: (options) => {
      transport = admissionTransport(options, admissions, config);
      return transport;
    },
  });
  peer.on('error', () => {});
  // Clients must use issued IDs; block unauthenticated ID allocation/discovery.
  app.use('/peerjs', (_request, response) => response.sendStatus(403), peer);
  app.use((_request, response) => response.sendStatus(404));
  server.drain = () => { draining = true; transport?.drain(); };
  return server;
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  try {
    const config = configuration();
    const server = createServer(config);
    server.listen(config.port, config.host, () => console.log('Admitted signalling server started'));
    server.on('error', () => { console.error('Signalling listener failed'); process.exitCode = 1; });
    for (const signal of ['SIGINT', 'SIGTERM']) process.once(signal, () => {
      server.drain();
      server.close();
      server.closeAllConnections();
      setTimeout(() => process.exit(0), 3000).unref();
    });
  } catch { console.error('Invalid signalling configuration'); process.exitCode = 1; }
}
