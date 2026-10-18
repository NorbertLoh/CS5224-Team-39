// Explicit local/CI fixture process, separate from the packaged runtime.
import { fixtures } from './fixtures.mjs';

const { server } = fixtures({ ttlMs: 60000 });
server.listen(9050, '0.0.0.0', () => console.log('V03 consultation test fixture started'));
for (const signal of ['SIGINT', 'SIGTERM']) process.once(signal, () => {
  server.close(); server.closeAllConnections();
});
