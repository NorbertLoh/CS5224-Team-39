import { test } from 'node:test';
import assert from 'node:assert/strict';
import { credentials, settings, uuid } from '../settings.mjs';

const local = { E2E_TARGET: 'local', E2E_BASE_URL: 'http://localhost:5173' };
const aws = { E2E_TARGET: 'aws-staging', E2E_BASE_URL: 'https://staging.example.test' };

test('no default destination: missing target or URL fails before browser launch', () => {
  assert.throws(() => settings({}), /E2E_TARGET/);
  assert.throws(() => settings({ E2E_TARGET: 'local' }), /E2E_BASE_URL/);
});
test('local loopback HTTP and deployed HTTPS are supported', () => {
  assert.equal(settings(local).baseURL, local.E2E_BASE_URL);
  assert.equal(settings(aws).ignoreHTTPSErrors, false);
  assert.equal(settings(local).allowWrites, false);
});
test('AWS rejects insecure TLS, loopback and accidental non-staging targets', () => {
  assert.throws(() => settings({ ...aws, E2E_IGNORE_HTTPS_ERRORS: 'true' }), /TLS/);
  assert.throws(() => settings({ ...aws, E2E_BASE_URL: 'https://localhost:8443' }), /deployed/);
  assert.throws(() => settings({ ...aws, E2E_BASE_URL: 'http://staging.example.test' }), /HTTPS/);
  assert.throws(() => settings({ ...aws, E2E_TARGET: 'production' }), /local or aws-staging/);
});
test('URLs cannot carry credentials or alter the intended origin/API path', () => {
  for (const url of ['https://a:b@example.test', 'https://example.test/path', 'https://example.test/?q=1', 'https://example.test/#x'])
    assert.throws(() => settings({ ...local, E2E_BASE_URL: url }), /origin/);
  for (const path of ['//other.test/api', '/api?x=y', '/api/../admin', 'https://other.test'])
    assert.throws(() => settings({ ...local, E2E_API_PATH: path }), /API path/);
});
test('write and provider switches require exact booleans and bounded waits', () => {
  assert.throws(() => settings({ ...local, E2E_ALLOW_WRITES: 'yes' }), /true or false/);
  for (const value of ['0', '901', 'NaN', '30.5'])
    assert.throws(() => settings({ ...local, E2E_PAYMENT_WAIT_SECONDS: value }), /30 to 900/);
  assert.throws(() => settings({ ...local, E2E_EXPECT_DELIVERY_STATUS: 'anything' }), /DELIVERY_STATUS/);
});
test('selected roles and evidence checks cannot silently skip missing credentials/IDs', () => {
  assert.throws(() => credentials('doctor', {}), /E2E_DOCTOR_EMAIL/);
  assert.throws(() => credentials('patient', { E2E_PATIENT_EMAIL: 'p@example.test' }), /E2E_PATIENT_PASSWORD/);
  assert.throws(() => uuid({ ID: 'not-an-id' }, 'ID'), /UUID/);
  assert.equal(uuid({ ID: '12345678-1234-1234-1234-123456789abc' }, 'ID'), '12345678-1234-1234-1234-123456789abc');
});
