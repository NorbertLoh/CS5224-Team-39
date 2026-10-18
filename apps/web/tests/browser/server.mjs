// Explicit fixture backend/discovery adapter; not imported by the production app.
import http from 'node:http';
import { fixtures } from '../../../../services/signalling/tests/fixtures.mjs';

const fixture = fixtures({ ttlMs: 60000 });
const subjects = new Map();
fixture.server.listen(9050, '0.0.0.0');
const server = http.createServer(async (request, response) => {
  const url = new URL(request.url, 'http://localhost');
  if (url.pathname === '/admissions') {
    let body = ''; for await (const chunk of request) body += chunk;
    const result = await fetch('http://127.0.0.1:9050/admissions', { method: 'POST',
      headers: { authorization: request.headers.authorization || '', 'content-type': 'application/json' }, body });
    const text = await result.text();
    if (result.status === 201) subjects.set(request.headers.authorization?.replace('Bearer fixture-', ''), JSON.parse(text).subject_id);
    response.writeHead(result.status, { 'content-type': 'application/json' }); response.end(text);
    return;
  }
  response.setHeader('content-type', 'application/json');
  if (url.pathname === '/ice') {
    const urls = process.env.U11_TURN_URL;
    response.end(JSON.stringify({ relay: Boolean(urls), servers: urls ? [{ urls,
      username: process.env.U11_TURN_USERNAME, credential: process.env.U11_TURN_CREDENTIAL }] : [] }));
    return;
  }
  if (url.pathname === '/counterpart') {
    // Doctor and patient were issued in order; map by each fixture subject ID.
    const active = [...fixture.grants.values()].filter((row) => row.consumed && !row.released
      && Date.parse(row.grant.expires_at) > Date.now());
    const targetSubject = url.searchParams.get('role') === 'patient' ? 'doctor-a' : 'patient-a';
    const marker = subjects.get(targetSubject);
    response.end(JSON.stringify({ peerId: active.find((row) => row.grant.subject_id === marker)?.grant.peer_id || null }));
    return;
  }
  if (url.pathname === '/reset') { fixture.state.revoked = false; fixture.grants.clear(); subjects.clear(); }
  if (url.pathname === '/revoke') fixture.state.revoked = true;
  response.end('{}');
});
server.listen(9051, '0.0.0.0');
for (const signal of ['SIGINT', 'SIGTERM']) process.once(signal, () => {
  for (const item of [server, fixture.server]) { item.close(); item.closeAllConnections(); }
});
