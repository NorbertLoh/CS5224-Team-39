import { EventEmitter } from 'node:events';
import { WebSocket, WebSocketServer } from 'ws';

// PeerServer 1.0.2's createWebSocketServer hook receives an event transport.
// Forward only admitted connections and validated frames, rather than trying to
// cancel PeerServer's public `message` event (which is only an observation hook).
export function admissionTransport(options, admissions) {
  const transport = new EventEmitter();
  const wss = new WebSocketServer({ noServer: true, maxPayload: 64 * 1024 });
  options.server.on('upgrade', (request, socket, head) => {
    let grant;
    try {
      const url = new URL(request.url, 'http://localhost');
      const query = url.searchParams;
      if (url.pathname !== options.path || query.get('key') !== 'x02'
        || ['id', 'token', 'key'].some((name) => query.getAll(name).length !== 1)) {
        throw new Error('Admission denied');
      }
      grant = admissions.consume(query.get('token'), query.get('id'));
    } catch {
      socket.end('HTTP/1.1 403 Forbidden\r\nConnection: close\r\nContent-Length: 0\r\n\r\n');
      return;
    }
    // Release a reservation even if an otherwise valid credential accompanies
    // a malformed WebSocket handshake. The credential remains consumed.
    const release = () => admissions.release(grant);
    socket.once('close', release);
    try {
      wss.handleUpgrade(request, socket, head, (wire) => {
        const peerSocket = new EventEmitter();
        peerSocket.send = (data) => {
          if (wire.readyState === WebSocket.OPEN) wire.send(data);
        };
        peerSocket.close = () => wire.close();
        let blocked = false;
        const deny = () => {
          blocked = true;
          // Stop routing immediately; don't wait for the close handshake.
          release();
          wire.close(1008, 'Admission denied');
          setTimeout(() => wire.terminate(), 250).unref();
        };
        const expiry = setTimeout(deny, admissions.remaining(grant));
        expiry.unref();
        wire.on('message', (data, binary) => {
          if (blocked) return;
          try {
            const message = JSON.parse(data.toString());
            if (binary || !admissions.allows(grant, message)) return deny();
            peerSocket.emit('message', data);
          } catch { deny(); }
        });
        wire.on('close', (...args) => {
          clearTimeout(expiry);
          release();
          peerSocket.emit('close', ...args);
        });
        wire.on('error', (error) => peerSocket.emit('error', error));
        transport.emit('connection', peerSocket, request);
      });
    } catch {
      release();
      socket.destroy();
    }
  });
  wss.on('error', (error) => transport.emit('error', error));
  return transport;
}
