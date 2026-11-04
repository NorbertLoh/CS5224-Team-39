export const roles = ['patient', 'doctor', 'clinic_admin', 'platform_admin'];

export function required(env, name) {
  if (!env[name]?.trim()) throw new Error(`Set ${name} before running this check.`);
  return env[name].trim();
}

function flag(env, name) {
  const value = env[name] ?? 'false';
  if (!['true', 'false'].includes(value)) throw new Error(`${name} must be true or false.`);
  return value === 'true';
}

export function settings(env = process.env) {
  const target = required(env, 'E2E_TARGET');
  if (!['local', 'aws-staging'].includes(target)) throw new Error('E2E_TARGET must be local or aws-staging.');
  const url = new URL(required(env, 'E2E_BASE_URL'));
  const loopback = ['localhost', '127.0.0.1', '[::1]'].includes(url.hostname);
  if (url.username || url.password || url.search || url.hash || url.pathname !== '/')
    throw new Error('E2E_BASE_URL must be an origin without credentials, path, query or fragment.');
  if (url.protocol !== 'https:' && !(target === 'local' && loopback && url.protocol === 'http:'))
    throw new Error('Use HTTPS, or loopback HTTP for local tests.');
  if (target === 'aws-staging' && loopback) throw new Error('AWS staging must use its deployed public URL.');
  const ignoreHTTPSErrors = flag(env, 'E2E_IGNORE_HTTPS_ERRORS');
  if (target === 'aws-staging' && ignoreHTTPSErrors) throw new Error('AWS staging must verify TLS certificates.');
  const apiPath = env.E2E_API_PATH || '/api/v1';
  if (!/^\/(?!\/)[a-zA-Z0-9/_-]+$/.test(apiPath)) throw new Error('E2E_API_PATH must be a same-origin API path.');
  const paymentWaitSeconds = Number(env.E2E_PAYMENT_WAIT_SECONDS || 480);
  if (!Number.isInteger(paymentWaitSeconds) || paymentWaitSeconds < 30 || paymentWaitSeconds > 900)
    throw new Error('E2E_PAYMENT_WAIT_SECONDS must be an integer from 30 to 900.');
  const deliveryStatus = env.E2E_EXPECT_DELIVERY_STATUS || 'submitted';
  if (!['submitted', 'picked_up', 'delivered', 'cancelled', 'failed'].includes(deliveryStatus))
    throw new Error('Unsupported E2E_EXPECT_DELIVERY_STATUS.');
  return {
    target, baseURL: url.origin, apiPath: apiPath.replace(/\/$/, ''), ignoreHTTPSErrors,
    allowWrites: flag(env, 'E2E_ALLOW_WRITES'), stripeTestMode: flag(env, 'E2E_STRIPE_TEST_MODE'),
    paymentWaitSeconds, deliveryStatus,
  };
}

export function credentials(role, env = process.env) {
  if (!roles.includes(role)) throw new Error('Unknown test role.');
  const prefix = `E2E_${role.toUpperCase()}`;
  return { email: required(env, `${prefix}_EMAIL`), password: required(env, `${prefix}_PASSWORD`) };
}

export function uuid(env, name) {
  const value = required(env, name);
  if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(value))
    throw new Error(`${name} must be a UUID.`);
  return value;
}
