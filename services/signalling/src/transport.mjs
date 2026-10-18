import { EventEmitter } from 'node:events';
import { WebSocket, WebSocketServer } from 'ws';
import { validCredential } from './admissions.mjs';

// Adapt X02's pre-registration bridge to V02's asynchronous service API. Neither
// PeerServer's public connection nor message observer can cancel registration/routing.
export function admissionTransport(options, admissions, config) {
  const transport = new EventEmitter();
  const wss = new WebSocketServer({ noServer: true, maxPayload: 64 * 1024 });
  const active = new Map();
  let pending = 0;
  let draining = false;
  const live = (grant) => !draining && active.get(grant.peerId)?.grant === grant
    && Date.now() < grant.expiresAt;
  const release = (grant) => {
    if (active.get(grant.peerId)?.grant === grant) active.delete(grant.peerId);
    void admissions.release(grant).catch(() => {});
  };
  const reject = (socket) => {
    if (!socket.destroyed) socket.end('HTTP/1.1 403 Forbidden\r\nConnection: close\r\nContent-Length: 0\r\n\r\n');
  };
  options.server.on('upgrade', async (request, socket, head) => {
    let grant;
    if (draining || pending + active.size >= config.maxConnections) return reject(socket);
    pending++;
    socket.pause();
    try {
      const url = new URL(request.url, 'http://localhost');
      const query = url.searchParams;
      if (url.pathname !== options.path || query.get('key') !== config.key
        || !config.origins.includes(request.headers.origin)
        || ['id', 'token', 'key'].some((name) => query.getAll(name).length !== 1)
        || !validCredential(query.get('token'), query.get('id'))) throw new Error('Admission denied');
      grant = await admissions.consume(query.get('token'), query.get('id'));
      if (draining || socket.destroyed || Date.now() >= grant.expiresAt || active.has(grant.peerId)
        || [...active.values()].some(({ grant: other }) => other.sessionId === grant.sessionId
          && other.subject === grant.subject)) throw new Error('Admission denied');
      let released = false;
      const finish = () => { if (!released) { released = true; release(grant); } };
      socket.once('close', finish);
      wss.handleUpgrade(request, socket, head, (wire) => {
        const bridge = new EventEmitter();
        const entry = { grant, deny: null };
        active.set(grant.peerId, entry);
        bridge.send = (data) => { if (live(grant) && wire.readyState === WebSocket.OPEN) wire.send(data); };
        bridge.close = () => wire.close();
        let blocked = false;
        const deny = () => {
          if (blocked) return;
          blocked = true;
          finish();
          wire.close(1008, 'Admission denied');
          setTimeout(() => wire.terminate(), 250).unref();
        };
        entry.deny = deny;
        const expiry = setTimeout(deny, Math.max(0, grant.expiresAt - Date.now()));
        expiry.unref();
        let checking = false;
        const interval = setInterval(async () => {
          if (checking || blocked) return;
          checking = true;
          try { await admissions.check(grant); if (!live(grant)) deny(); }
          catch { deny(); }
          finally { checking = false; }
        }, config.checkIntervalMs);
        interval.unref();
        let queue = Promise.resolve();
        let queued = 0;
        wire.on('message', (data, binary) => {
          if (blocked) return;
          if (++queued > 16) return deny();
          queue = queue.then(async () => {
            if (blocked || binary || !live(grant)) return deny();
            try {
              const message = JSON.parse(data.toString());
              if (!message || typeof message !== 'object' || Array.isArray(message)
                || (message.src !== undefined && message.src !== grant.peerId)) return deny();
              let target;
              if (message.type === 'HEARTBEAT') {
                if (message.dst !== undefined) return deny();
              } else {
                if (!['OFFER', 'ANSWER', 'CANDIDATE', 'LEAVE', 'EXPIRE'].includes(message.type)) return deny();
                target = active.get(message.dst)?.grant;
                if (!target || target.subject === grant.subject || target.sessionId !== grant.sessionId
                  || target.tenantId !== grant.tenantId || target.appointmentId !== grant.appointmentId
                  || !live(target)) return deny();
              }
              await admissions.check(grant);
              if (target) await admissions.check(target);
              if (!live(grant) || (target && !live(target))) return deny();
              bridge.emit('message', data);
            } catch { deny(); }
          }).catch(deny).finally(() => { queued--; });
        });
        wire.on('close', (...args) => {
          blocked = true;
          clearTimeout(expiry);
          clearInterval(interval);
          finish();
          bridge.emit('close', ...args);
        });
        // Do not forward raw socket errors that might contain credentials.
        wire.on('error', deny);
        transport.emit('connection', bridge, request);
      });
      socket.resume();
    } catch {
      if (grant) release(grant);
      reject(socket);
    } finally { pending--; }
  });
  wss.on('error', () => {});
  // Discovery uses the consumed admission as a scoped bearer capability. Never
  // expose PeerServer's global peer list or accept appointment/participant IDs.
  transport.counterpart = async (token, peerId) => {
    const grant = active.get(peerId)?.grant;
    if (!validCredential(token, peerId) || !grant || grant.token !== token || !live(grant)) {
      throw new Error('Admission denied');
    }
    await admissions.check(grant);
    if (!live(grant)) throw new Error('Admission denied');
    const target = [...active.values()].map((entry) => entry.grant).find((other) =>
      other.subject !== grant.subject && other.sessionId === grant.sessionId
      && other.tenantId === grant.tenantId && other.appointmentId === grant.appointmentId
      && live(other));
    if (!target) return null;
    await admissions.check(target);
    if (!live(grant)) throw new Error('Admission denied');
    return live(target) ? target.peerId : null;
  };
  transport.drain = () => {
    draining = true;
    for (const { deny } of [...active.values()]) deny();
  };
  return transport;
}
