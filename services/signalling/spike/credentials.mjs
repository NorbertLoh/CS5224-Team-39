import { createHmac } from 'node:crypto';
import { pathToFileURL } from 'node:url';

export function turnCredentials(secret, label = 'x01', ttl = 600, now = Date.now()) {
  if (!secret || secret.length < 32) throw new Error('TURN_SHARED_SECRET must contain at least 32 characters');
  if (!/^[a-zA-Z0-9_-]{1,32}$/.test(label)) throw new Error('Use a short non-identifying label');
  if (!Number.isInteger(ttl) || ttl < 60 || ttl > 3600) throw new Error('TTL must be 60–3600 seconds');
  const expires = Math.floor(now / 1000) + ttl;
  const username = `${expires}:${label}`;
  return { username, credential: createHmac('sha1', secret).update(username).digest('base64'),
    expiresAt: new Date(expires * 1000).toISOString() };
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  try {
    console.log(JSON.stringify(turnCredentials(process.env.TURN_SHARED_SECRET,
      process.argv[2] || 'x01', Number(process.argv[3] || 600)), null, 2));
  } catch (error) {
    console.error(error.message);
    process.exitCode = 1;
  }
}
