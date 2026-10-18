export function configuration(env = process.env) {
  const environment = env.SIGNALLING_ENVIRONMENT || 'local';
  if (!['local', 'test', 'production'].includes(environment)) throw new Error('Invalid environment');
  const url = new URL(env.CONSULTATION_URL || 'http://127.0.0.1:8004');
  if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password
    || url.search || url.hash || (environment === 'production' && url.protocol !== 'https:')) {
    throw new Error('Invalid consultation URL');
  }
  const secret = env.SIGNALLING_SECRET;
  if (!secret || Buffer.byteLength(secret) < 32) throw new Error('SIGNALLING_SECRET needs 32 bytes');
  const origins = (env.SIGNALLING_ORIGINS || 'https://localhost:8443').split(',');
  for (const origin of origins) {
    const parsed = new URL(origin);
    if (parsed.origin !== origin || parsed.protocol !== 'https:') throw new Error('Use exact HTTPS origins');
  }
  const port = Number(env.SIGNALLING_PORT || 9000);
  if (!Number.isInteger(port) || port < 0 || port > 65535) throw new Error('Invalid port');
  return { url: url.href.replace(/\/$/, ''), secret, origins, port,
    host: env.SIGNALLING_HOST || '127.0.0.1', key: 'telelink',
    timeoutMs: 3000, checkIntervalMs: 2000, maxConnections: 100 };
}
