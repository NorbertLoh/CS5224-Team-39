// Explicit test-only consultation API adapter. Never copied into the runtime image.
import http from 'node:http';
import { createHmac, randomBytes, randomUUID } from 'node:crypto';

export const SECRET = 'v03-test-only-signalling-secret-at-least-32-bytes';
export function fixtures({ ttlMs = 15000 } = {}) {
  const state = { unavailable: false, revoked: false, releases: 0, checks: 0, consumes: 0 };
  const grants = new Map();
  const subjects = new Map();
  const appointments = new Map();
  const issue = (subject = 'patient-a', appointment = 'a') => {
    if (!subjects.has(subject)) subjects.set(subject, randomUUID());
    if (!appointments.has(appointment)) appointments.set(appointment, {
      tenant_id: randomUUID(), session_id: randomUUID(), appointment_id: randomUUID(),
    });
    const token = randomBytes(32).toString('base64url');
    const grant = { ...appointments.get(appointment), peer_id: randomUUID(),
      subject_id: subjects.get(subject), expires_at: new Date(Date.now() + ttlMs).toISOString() };
    grants.set(token, { grant, consumed: false, released: false });
    return { ...grant, token };
  };
  const server = http.createServer(async (request, response) => {
    const send = (status, body) => { response.writeHead(status, { 'content-type': 'application/json' });
      response.end(body === undefined ? '' : JSON.stringify(body)); };
    try {
      if (request.url === '/healthz') return send(200, { fixtures: true });
      let body = '';
      for await (const chunk of request) { body += chunk; if (body.length > 4096) return send(413); }
      body = JSON.parse(body);
      // Browser fixture issuer; unrelated/unpaid callers are never admitted.
      if (request.url === '/admissions') {
        const subject = request.headers.authorization?.replace('Bearer fixture-', '');
        if (!['patient-a', 'doctor-a', 'patient-b', 'doctor-b'].includes(subject)) return send(403);
        const appointment = subject.endsWith('-a') ? 'a' : 'b';
        if (body.appointment_id !== appointment) return send(403);
        if ([...grants.values()].some((row) => row.grant.subject_id === subjects.get(subject)
          && row.consumed && !row.released && Date.now() < Date.parse(row.grant.expires_at))) return send(409);
        return send(201, issue(subject, appointment));
      }
      const token = request.headers.authorization?.replace('Bearer ', '') || '';
      const [header, payload, signature] = token.split('.');
      if (createHmac('sha256', SECRET).update(`${header}.${payload}`).digest('base64url') !== signature) return send(401);
      const claims = JSON.parse(Buffer.from(payload, 'base64url'));
      if (claims.sub !== 'signalling' || claims.iss !== 'telelink-service:signalling'
        || claims.aud !== 'telelink-consultation-admission' || claims.exp <= Date.now() / 1000) return send(401);
      if (state.unavailable) return send(503);
      const row = grants.get(body.token);
      if (!row || row.grant.peer_id !== body.peer_id) return send(403);
      if (request.url === '/internal/admissions/release') {
        row.released = true; state.releases++; return send(204);
      }
      if (row.released || state.revoked || Date.now() >= Date.parse(row.grant.expires_at)) return send(403);
      if (request.url === '/internal/admissions/consume') {
        if (row.consumed || [...grants.values()].some((other) => other !== row && other.consumed
          && !other.released && other.grant.subject_id === row.grant.subject_id
          && other.grant.session_id === row.grant.session_id
          && Date.now() < Date.parse(other.grant.expires_at))) return send(403);
        row.consumed = true; state.consumes++;
      } else if (request.url === '/internal/admissions/check') {
        if (!row.consumed) return send(403);
        state.checks++;
      } else return send(404);
      return send(200, row.grant);
    } catch { send(400); }
  });
  return { server, issue, state, grants };
}
