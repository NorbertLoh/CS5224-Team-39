import express from 'express';
import http from 'node:http';
import { pathToFileURL } from 'node:url';
import { ExpressPeerServer } from 'peer';
import { Admissions } from './admissions.mjs';
import { configuration } from './config.mjs';
import { admissionTransport } from './transport.mjs';
import { Matchmaker, discoverInternalUrl, nodePattern } from './matchmaker.mjs';
import { TaskProtection } from './protection.mjs';

export function createServer(config, admissions = new Admissions(config)) {
  const app = express();
  const server = http.createServer({ requestTimeout: 10000, headersTimeout: 10000 }, app);
  let transport;
  let draining = false;
  const registry = config.matchmaker ? new Matchmaker(config) : null;
  if (registry) config.router = registry;
  app.disable('x-powered-by');
  app.use((_request, response, next) => {
    response.set({ 'Cache-Control': 'no-store', 'Referrer-Policy': 'no-referrer',
      'X-Content-Type-Options': 'nosniff' });
    next();
  });
  app.get('/healthz', (_request, response) => {
    const healthy = !draining && (!registry || registry.live());
    response.status(healthy ? 200 : 503).json({ status: healthy ? 'ok' : 'unavailable', service: 'signalling' });
  });
  const peer = ExpressPeerServer(server, {
    path: '/', key: config.key, allow_discovery: false, concurrent_limit: config.maxConnections,
    createWebSocketServer: (options) => {
      transport = admissionTransport(options, admissions, config);
      return transport;
    },
  });
  peer.on('error', () => {});
  let discovering = 0;
  if (registry) app.post(new RegExp(`^/peerjs/nodes/(${nodePattern})/counterpart$`),
    express.json({ limit: '1kb' }), async (request, response, next) => {
      const nodeId = request.params[0];
      if (draining || !registry.live() || !config.origins.includes(request.headers.origin)) return response.sendStatus(403);
      if (nodeId === config.nodeId) { request.url = '/peerjs/counterpart'; return next(); }
      if (request.headers['x-telelink-proxy-hop']) return response.sendStatus(403);
      try { response.json(await registry.counterpart(nodeId, request.body, request.headers.origin)); }
      catch { response.sendStatus(503); }
    });
  app.post('/peerjs/counterpart', express.json({ limit: '1kb' }), async (request, response) => {
    if (draining || !config.origins.includes(request.headers.origin)
      || discovering >= config.maxConnections || !request.body
      || Object.keys(request.body).sort().join(',') !== 'peer_id,token') {
      return response.sendStatus(403);
    }
    discovering++;
    try {
      const peerId = await transport.counterpart(request.body.token, request.body.peer_id);
      response.json({ peer_id: peerId });
    } catch { response.sendStatus(403); }
    finally { discovering--; }
  });
  // Clients must use issued IDs; block unauthenticated ID allocation/discovery.
  app.use('/peerjs', (_request, response) => response.sendStatus(403), peer);
  app.use((_request, response) => response.sendStatus(404));
  // Parser/limit errors must not reflect bodies or use Express's raw error logger.
  app.use((_error, _request, response, _next) => response.sendStatus(400));
  server.drain = () => { draining = true; registry?.close(); transport?.drain(); };
  server.registry = registry;
  server.activeCount = () => (transport?.activeCount() || 0) + (registry?.proxies.size || 0);
  server.pendingCount = () => (transport?.pendingCount() || 0) + (registry?.pending || 0);
  return server;
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  try {
    const config = configuration();
    if (config.matchmaker) {
      config.protection = new TaskProtection();
      if (config.requireTaskProtection && !config.protection.uri) throw new Error('ECS agent required');
    }
    const server = createServer(config);
    if (config.matchmaker) config.internalUrl = await discoverInternalUrl(config);
    await new Promise((resolve, reject) => {
      server.once('error', reject);
      server.listen(config.port, config.host, resolve);
    });
    if (server.registry) {
      // A process gets one boot identity. Never revive an expired identity.
      await server.registry.heartbeat();
      let pending = false;
      let idleSince = Date.now();
      const heartbeat = setInterval(async () => {
        if (pending) return;
        pending = true;
        try {
          await server.registry.heartbeat();
          if (server.activeCount() > 0) {
            idleSince = Date.now();
            await config.protection.ensure();
          } else if (server.pendingCount() === 0 && Date.now() - idleSince > 15000) {
            await config.protection.release();
          }
        }
        catch { if (!server.registry.live()) { server.drain(); process.exit(1); } }
        finally { pending = false; }
      }, 3000);
      heartbeat.unref();
    }
    console.log('Admitted signalling server started');
    server.on('error', () => { console.error('Signalling listener failed'); process.exitCode = 1; });
    for (const signal of ['SIGINT', 'SIGTERM']) process.once(signal, async () => {
      const finish = () => { server.drain(); server.close(); server.closeAllConnections(); process.exit(0); };
      if (!server.registry) { finish(); return; }
      server.registry.draining = true;
      try { await server.registry.heartbeat(); } catch { finish(); return; }
      const deadline = Date.now() + config.drainMs;
      const timer = setInterval(() => {
        if (server.activeCount() + server.pendingCount() === 0 || Date.now() >= deadline) { clearInterval(timer); finish(); }
      }, 250);
    });
  } catch { console.error('Signalling startup failed'); process.exit(1); }
}
