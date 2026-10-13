export interface AuthConfig {
  clientId: string
  issuer: string
  authorizeUrl: string
  tokenUrl: string
  logoutUrl: string
  apiUrl: string
  redirectUri: string
  logoutUri: string
}

export interface Session {
  accessToken: string
  refreshToken: string
  expiresAt: number
}

const pendingKey = 'telelink.pkce'
const sessionKey = 'telelink.session'
const pendingLifetime = 10 * 60 * 1000
const expiredMessage = 'Your session expired. Please sign in again.'
const refreshes = new WeakMap<Storage, Promise<Session>>()

function base64url(bytes: Uint8Array): string {
  return btoa(String.fromCharCode(...bytes))
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=+$/, '')
}

export async function pkceChallenge(verifier: string): Promise<string> {
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(verifier))
  return base64url(new Uint8Array(digest))
}

function random(): string {
  return base64url(crypto.getRandomValues(new Uint8Array(32)))
}

export function authConfig(): AuthConfig | null {
  const env = import.meta.env
  if (!env?.VITE_COGNITO_CLIENT_ID) return null
  const issuer = env.VITE_COGNITO_ISSUER
  const oauth = env.VITE_COGNITO_OAUTH_BASE_URL
  const api = env.VITE_COGNITO_API_URL
  if (!issuer || !oauth || !api) throw new Error('Complete the Cognito environment configuration.')

  for (const value of [issuer, oauth, api]) {
    const url = new URL(value)
    const localHttp = env.DEV && url.protocol === 'http:' && ['localhost', '127.0.0.1'].includes(url.hostname)
    const hasExtras = url.username || url.password || url.search || url.hash
    if (hasExtras || (url.protocol !== 'https:' && !localHttp)) {
      throw new Error('Cognito URLs require HTTPS, or localhost HTTP in development.')
    }
  }
  const base = oauth.replace(/\/+$/, '')
  return {
    clientId: env.VITE_COGNITO_CLIENT_ID,
    issuer: issuer.replace(/\/+$/, ''),
    authorizeUrl: `${base}/oauth2/authorize`,
    tokenUrl: `${base}/oauth2/token`,
    logoutUrl: `${base}/logout`,
    apiUrl: api,
    redirectUri: `${location.origin}/auth/callback`,
    logoutUri: `${location.origin}/`,
  }
}

function readStored(key: string, storage: Storage) {
  try {
    return JSON.parse(storage.getItem(key) || 'null')
  } catch {
    return null
  }
}

export function readSession(storage: Storage = sessionStorage): Session | null {
  const session = readStored(sessionKey, storage)
  if (
    session &&
    typeof session.accessToken === 'string' &&
    typeof session.refreshToken === 'string' &&
    Number.isFinite(session.expiresAt)
  )
    return session
  storage.removeItem(sessionKey)
  return null
}

export function clearSession(storage: Storage = sessionStorage): void {
  storage.removeItem(sessionKey)
  storage.removeItem(pendingKey)
}

function saveSession(session: Session, storage: Storage): Session {
  storage.setItem(sessionKey, JSON.stringify(session))
  return session
}

async function post(url: string, body: BodyInit, headers: Record<string, string>): Promise<Response> {
  const response = await fetch(url, {
    method: 'POST',
    body,
    headers,
    credentials: 'omit',
    cache: 'no-store',
    redirect: 'error',
    signal: AbortSignal.timeout(15000),
  })
  if (!response.ok) throw new Error('Authentication request failed. Please sign in again.')
  return response
}

function cognito(config: AuthConfig, action: string, body: object): Promise<Response> {
  return post(config.apiUrl, JSON.stringify(body), {
    'Content-Type': 'application/x-amz-json-1.1',
    'X-Amz-Target': `AWSCognitoIdentityProviderService.${action}`,
  })
}

function validateSession(config: AuthConfig, accessToken: unknown, refreshToken: unknown, expiresIn: unknown): Session {
  if (
    typeof accessToken !== 'string' ||
    typeof refreshToken !== 'string' ||
    !refreshToken ||
    typeof expiresIn !== 'number' ||
    !Number.isFinite(expiresIn) ||
    expiresIn <= 0
  ) {
    throw new Error('Invalid sign-in response. Please sign in again.')
  }
  // Browser checks catch configuration mistakes; the API verifies the signature.
  const payload = accessToken.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')
  const bytes = Uint8Array.from(atob(payload), (character) => character.charCodeAt(0))
  const claims = JSON.parse(new TextDecoder().decode(bytes))
  if (
    claims.iss !== config.issuer ||
    claims.client_id !== config.clientId ||
    claims.token_use !== 'access' ||
    typeof claims.exp !== 'number' ||
    claims.exp * 1000 <= Date.now()
  ) {
    throw new Error('Invalid access token. Please sign in again.')
  }
  return { accessToken, refreshToken, expiresAt: Math.min(claims.exp * 1000, Date.now() + expiresIn * 1000) }
}

export async function beginLogin(config: AuthConfig, storage: Storage = sessionStorage): Promise<string> {
  const verifier = random()
  const state = random()
  const challenge = await pkceChallenge(verifier)
  storage.setItem(pendingKey, JSON.stringify({ verifier, state, createdAt: Date.now() }))
  const url = new URL(config.authorizeUrl)
  url.search = new URLSearchParams({
    client_id: config.clientId,
    response_type: 'code',
    redirect_uri: config.redirectUri,
    scope: 'openid email profile',
    state,
    code_challenge: challenge,
    code_challenge_method: 'S256',
  }).toString()
  return url.toString()
}

export async function finishLogin(
  config: AuthConfig,
  search: string,
  storage: Storage = sessionStorage,
): Promise<Session> {
  const pending = readStored(pendingKey, storage)
  storage.removeItem(pendingKey) // Consume once, including failed attempts.
  const params = new URLSearchParams(search)
  const age = Date.now() - pending?.createdAt
  if (
    !pending ||
    typeof pending.verifier !== 'string' ||
    !Number.isFinite(pending.createdAt) ||
    age < 0 ||
    age > pendingLifetime ||
    !params.get('state') ||
    params.get('state') !== pending.state
  ) {
    throw new Error('Sign-in expired or state did not match. Please try again.')
  }
  const code = params.get('code')
  if (params.has('error') || !code) throw new Error('Sign-in was not completed. Please try again.')
  const response = await post(
    config.tokenUrl,
    new URLSearchParams({
      grant_type: 'authorization_code',
      client_id: config.clientId,
      redirect_uri: config.redirectUri,
      code,
      code_verifier: pending.verifier,
    }),
    { 'Content-Type': 'application/x-www-form-urlencoded' },
  )
  const tokens = await response.json()
  return saveSession(validateSession(config, tokens.access_token, tokens.refresh_token, tokens.expires_in), storage)
}

export function refreshSession(
  config: AuthConfig,
  session: Session,
  storage: Storage = sessionStorage,
): Promise<Session> {
  const existing = refreshes.get(storage)
  if (existing) return existing
  const pending = performRefresh(config, session, storage).finally(() => refreshes.delete(storage))
  refreshes.set(storage, pending)
  return pending
}

async function performRefresh(config: AuthConfig, session: Session, storage: Storage): Promise<Session> {
  const previous = storage.getItem(sessionKey)
  if (!previous) throw new Error('Session changed during refresh.')
  let response: Response
  try {
    response = await cognito(config, 'InitiateAuth', {
      AuthFlow: 'REFRESH_TOKEN_AUTH',
      ClientId: config.clientId,
      AuthParameters: { REFRESH_TOKEN: session.refreshToken },
    })
  } catch {
    throw new Error(expiredMessage)
  }
  const tokens = (await response.json()).AuthenticationResult
  const refreshed = validateSession(
    config,
    tokens?.AccessToken,
    tokens?.RefreshToken || session.refreshToken,
    tokens?.ExpiresIn,
  )
  // A late refresh must never undo logout or overwrite a newer session.
  if (storage.getItem(sessionKey) !== previous) throw new Error('Session changed during refresh.')
  return saveSession(refreshed, storage)
}

export async function endSession(
  config: AuthConfig,
  session: Session | null,
  storage: Storage = sessionStorage,
): Promise<string> {
  clearSession(storage)
  try {
    if (session) await cognito(config, 'RevokeToken', { ClientId: config.clientId, Token: session.refreshToken })
  } catch {
    storage.setItem('telelink.logout-warning', 'Signed out locally. Token revocation could not be confirmed.')
  }
  const url = new URL(config.logoutUrl)
  url.search = new URLSearchParams({ client_id: config.clientId, logout_uri: config.logoutUri }).toString()
  return url.toString()
}
