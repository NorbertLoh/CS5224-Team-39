import { createHmac } from 'node:crypto';

const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
export const validCredential = (token, peerId) => typeof token === 'string'
  && /^[A-Za-z0-9_-]{43}$/.test(token) && typeof peerId === 'string' && uuid.test(peerId);

export function serviceToken(secret) {
  const now = Math.floor(Date.now() / 1000);
  const encode = (value) => Buffer.from(JSON.stringify(value)).toString('base64url');
  const content = `${encode({ alg: 'HS256', typ: 'JWT' })}.${encode({
    iss: 'telelink-service:signalling', sub: 'signalling', aud: 'telelink-consultation-admission',
    iat: now, exp: now + 60,
  })}`;
  return `${content}.${createHmac('sha256', secret).update(content).digest('base64url')}`;
}

export class Admissions {
  constructor(config) { this.config = config; }

  async call(action, token, peerId) {
    if (!validCredential(token, peerId)) throw new Error('Admission denied');
    const response = await fetch(`${this.config.url}/internal/admissions/${action}`, {
      method: 'POST', redirect: 'error', signal: AbortSignal.timeout(this.config.timeoutMs),
      headers: { authorization: `Bearer ${serviceToken(this.config.secret)}`, 'content-type': 'application/json' },
      body: JSON.stringify({ token, peer_id: peerId }),
    });
    if (action === 'release' && response.status === 204) return;
    if (response.status !== 200) {
      await response.body?.cancel();
      throw new Error('Admission denied');
    }
    // Bound even a malformed upstream response before parsing it.
    let bytes = 0;
    const chunks = [];
    for await (const chunk of response.body) {
      bytes += chunk.length;
      if (bytes > 4096) throw new Error('Invalid admission response');
      chunks.push(chunk);
    }
    const lease = JSON.parse(Buffer.concat(chunks).toString());
    if (!lease || ['peer_id', 'subject_id', 'appointment_id', 'tenant_id', 'session_id']
      .some((field) => typeof lease[field] !== 'string' || !uuid.test(lease[field]))
      || lease.peer_id !== peerId || typeof lease.expires_at !== 'string') {
      throw new Error('Invalid admission response');
    }
    const expiresAt = Date.parse(lease.expires_at);
    if (!Number.isFinite(expiresAt) || expiresAt <= Date.now() || expiresAt > Date.now() + 300000) {
      throw new Error('Invalid admission lifetime');
    }
    return { peerId, subject: lease.subject_id, appointmentId: lease.appointment_id,
      tenantId: lease.tenant_id, sessionId: lease.session_id, expiresAt, token };
  }

  consume(token, peerId) { return this.call('consume', token, peerId); }

  async check(grant) {
    const current = await this.call('check', grant.token, grant.peerId);
    if (['subject', 'appointmentId', 'tenantId', 'sessionId', 'expiresAt']
      .some((key) => current[key] !== grant[key])) throw new Error('Admission changed');
  }

  async release(grant) {
    // A lost response must never trigger a second consume. Release is idempotent
    // and gets bounded retries; expiry recovers a reservation if all fail.
    for (let attempt = 0; attempt < 3; attempt++) {
      try { await this.call('release', grant.token, grant.peerId); return; }
      catch { if (Date.now() >= grant.expiresAt) return; }
    }
  }
}
