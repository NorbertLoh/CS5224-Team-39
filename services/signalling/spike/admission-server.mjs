import express from 'express';
import http from 'node:http';
import { ExpressPeerServer } from 'peer';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { createAdmissions } from './admission.mjs';
import { admissionTransport } from './admission-transport.mjs';

export function fixtureAppointments(now = Date.now()) {
  const appointment = (participants, overrides = {}) => ({
    participants, status: 'booked', payment: 'paid', joinFrom: now - 60000,
    joinUntil: now + 3600000, ...overrides,
  });
  return new Map([
    ['appointment-a', appointment(['patient-a', 'doctor-a'])],
    ['appointment-b', appointment(['patient-b', 'doctor-b'])],
    ['unpaid', appointment(['patient-a', 'doctor-a'], { payment: 'pending' })],
    ['cancelled', appointment(['patient-a', 'doctor-a'], { status: 'cancelled' })],
    ['too-early', appointment(['patient-a', 'doctor-a'], { joinFrom: now + 600000 })],
    ['too-late', appointment(['patient-a', 'doctor-a'], { joinUntil: now })],
  ]);
}

export function createAdmissionServer({ ttlSeconds = 60 } = {}) {
  const admissions = createAdmissions(fixtureAppointments(), { ttlSeconds });
  const app = express();
  const server = http.createServer(app);
  app.disable('x-powered-by');
  app.use((_req, res, next) => {
    res.set({ 'Cache-Control': 'no-store', 'Referrer-Policy': 'no-referrer',
      'X-Content-Type-Options': 'nosniff',
      'Content-Security-Policy': "default-src 'none'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'" });
    next();
  });
  app.use(express.json({ limit: '2kb' }));
  app.get('/healthz', (_req, res) => res.json({ status: 'ok', spike: 'X02', fixtures: true }));
  // Explicit test identities, NOT authentication. Never deploy this fixture issuer.
  const identities = new Map(['patient-a', 'doctor-a', 'patient-b', 'doctor-b', 'unrelated']
    .map((subject) => [`Bearer fixture-${subject}`, subject]));
  app.post('/fixture/admissions', (req, res) => {
    const subject = identities.get(req.headers.authorization);
    if (!subject) return res.sendStatus(401);
    try { res.json(admissions.issue(subject, req.body?.appointmentId)); }
    catch { res.sendStatus(403); }
  });
  app.get('/vendor/peerjs.min.js', (_req, res) => res.sendFile(
    fileURLToPath(new URL('./node_modules/peerjs/dist/peerjs.min.js', import.meta.url)), { dotfiles: 'allow' }));
  app.get('/', (_req, res) => res.type('html').send(
    '<!doctype html><title>X02 fixture admission test</title><script src="/vendor/peerjs.min.js"></script>'));
  const peer = ExpressPeerServer(server, {
    path: '/', key: 'x02', allow_discovery: false, concurrent_limit: 10,
    createWebSocketServer: (options) => admissionTransport(options, admissions),
  });
  // Invalid wire input is filtered before PeerServer; don't expose payloads in logs.
  peer.on('error', () => {});
  app.use('/peerjs', peer);
  return server;
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const port = Number(process.env.X02_PORT || 9002);
  if (!Number.isInteger(port) || port < 0 || port > 65535) throw new Error('Invalid X02_PORT');
  const server = createAdmissionServer({ ttlSeconds: Number(process.env.X02_TTL_SECONDS || 60) });
  // Intentionally fixed loopback: fixture credentials must never be internet reachable.
  server.listen(port, '127.0.0.1', () => console.log(`X02 fixtures: http://127.0.0.1:${server.address().port}`));
  for (const signal of ['SIGINT', 'SIGTERM']) process.on(signal, () => {
    server.close();
    server.closeAllConnections();
    setTimeout(() => process.exit(0), 500).unref();
  });
}
