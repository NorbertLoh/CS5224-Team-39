// Local/CI only. Coturn binds strictly to loopback, without published host ports.
import { mkdtempSync, writeFileSync, unlinkSync, rmdirSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { createHmac, randomBytes } from 'node:crypto';
import { spawnSync } from 'node:child_process';

const directory = mkdtempSync(join(tmpdir(), 'telelink-u11-turn-'));
const file = join(directory, 'turnserver.conf');
const secret = randomBytes(32).toString('base64url');
const username = `${Math.floor(Date.now() / 1000) + 900}:u11`;
const credential = createHmac('sha1', secret).update(username).digest('base64');
const name = `telelink-u11-turn-${process.pid}`;
writeFileSync(file, ['listening-ip=127.0.0.1', 'relay-ip=127.0.0.1', 'listening-port=3480',
  'min-port=49200', 'max-port=49220', 'fingerprint', 'use-auth-secret', `static-auth-secret=${secret}`,
  'realm=u11.local', 'no-tls', 'no-dtls', 'no-cli', 'allow-loopback-peers',
  'no-multicast-peers', 'no-tcp-relay', 'relay-threads=1'].join('\n'));
try {
  const started = spawnSync('docker', ['run', '-d', '--rm', '--name', name, '--network', 'host',
    '-v', `${file.replaceAll('\\', '/')}:/etc/coturn/turnserver.conf:ro`,
    'coturn/coturn:4.6.3@sha256:71c3c990283385567f11794ee692e3a47b66fd9b0bb39e42afbe776e331dd888',
    '-c', '/etc/coturn/turnserver.conf'], { encoding: 'utf8' });
  if (started.status !== 0) throw new Error('Loopback coturn could not start');
  for (const transport of (process.env.U11_TEST_TRANSPORTS || 'udp,tcp').split(',')) {
    console.log(`U11 loopback forced-relay check: ${transport}`);
    const result = spawnSync(process.execPath, [resolve('node_modules/@playwright/test/cli.js'), 'test',
      '--config', 'playwright.video.config.mjs', '--grep', 'room exchanges actual audio/video'], {
      stdio: 'inherit', env: { ...process.env, U11_TURN_URL: `turn:127.0.0.1:3480?transport=${transport}`,
        U11_TURN_USERNAME: username, U11_TURN_CREDENTIAL: credential },
    });
    if (result.status !== 0) {
      const logs = spawnSync('docker', ['logs', name], { encoding: 'utf8' });
      console.log('Redacted TURN diagnostics', { authenticationErrors: (logs.stdout.match(/wrong|unauthor|401|438/gi) || []).length,
        errors: (logs.stdout.match(/error/gi) || []).length });
      process.exitCode = 1; break;
    }
  }
} finally {
  spawnSync('docker', ['stop', name], { stdio: 'ignore' });
  unlinkSync(file); rmdirSync(directory);
}
