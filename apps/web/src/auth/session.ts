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
const maxAge = 10 * 60 * 1000

function base64url(bytes: Uint8Array): string {
  return btoa(String.fromCharCode(...bytes))
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=+$/, '')
}

export async function pkceChallenge(verifier: string): Promise<string> {
  return base64url(
    new Uint8Array(
      await crypto.subtle.digest('SHA-256', new TextEncoder().encode(verifier)),
    ),
  )
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
  if (!issuer || !oauth || !api)
    throw new Error('Complete the Cognito environment configuration.')
  for (const value of [issuer, oauth, api]) {
    const url = new URL(value)
    if (
      url.username ||
      url.password ||
      url.search ||
      url.hash ||
      (url.protocol !== 'https:' &&
        !(
          import.meta.env.DEV &&
          url.protocol === 'http:' &&
          ['localhost', '127.0.0.1'].includes(url.hostname)
        ))
    ) {
      throw new Error(
        'Cognito URLs require HTTPS, or localhost HTTP in development.',
      )
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

export async function beginLogin(
  config: AuthConfig,
  storage: Storage = sessionStorage,
): Promise<string> {
  const verifier = random()
  const state = random()
  const challenge = await pkceChallenge(verifier)
  storage.setItem(
    pendingKey,
    JSON.stringify({ verifier, state, createdAt: Date.now() }),
  )
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

function validateSession(
  config: AuthConfig,
  accessToken: unknown,
  refreshToken: unknown,
  expiresIn: unknown,
): Session {
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
  // These checks catch configuration/response mistakes. The API verifies the signature.
  const part = accessToken.split('.')[1]
  const claims = JSON.parse(
    new TextDecoder().decode(
      Uint8Array.from(atob(part.replace(/-/g, '+').replace(/_/g, '/')), (c) =>
        c.charCodeAt(0),
      ),
    ),
  )
  if (
    claims.iss !== config.issuer ||
    claims.client_id !== config.clientId ||
    claims.token_use !== 'access' ||
    typeof claims.exp !== 'number' ||
    claims.exp * 1000 <= Date.now()
  )
    throw new Error('Invalid access token. Please sign in again.')
  return {
    accessToken,
    refreshToken,
    expiresAt: Math.min(claims.exp * 1000, Date.now() + expiresIn * 1000),
  }
}

export async function finishLogin(
  config: AuthConfig,
  search: string,
  storage: Storage = sessionStorage,
): Promise<Session> {
  const raw = storage.getItem(pendingKey)
  storage.removeItem(pendingKey) // one attempt; replay requires a new login
  const params = new URLSearchParams(search)
  const pending = raw ? JSON.parse(raw) : null
  if (
    !pending ||
    typeof pending.verifier !== 'string' ||
    !Number.isFinite(pending.createdAt) ||
    Date.now() < pending.createdAt ||
    Date.now() - pending.createdAt > maxAge ||
    !params.get('state') ||
    params.get('state') !== pending.state
  )
    throw new Error('Sign-in expired or state did not match. Please try again.')
  if (params.has('error') || !params.get('code'))
    throw new Error('Sign-in was not completed. Please try again.')
  const response = await fetch(config.tokenUrl, {
    method: 'POST',
    credentials: 'omit',
    cache: 'no-store',
    redirect: 'error',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({
      grant_type: 'authorization_code',
      client_id: config.clientId,
      redirect_uri: config.redirectUri,
      code: params.get('code')!,
      code_verifier: pending.verifier,
    }),
    signal: AbortSignal.timeout(15000),
  })
  if (!response.ok) throw new Error('Sign-in failed. Please try again.')
  const data = await response.json()
  const session = validateSession(
    config,
    data.access_token,
    data.refresh_token,
    data.expires_in,
  )
  storage.setItem(sessionKey, JSON.stringify(session))
  return session
}

export function readSession(storage: Storage = sessionStorage): Session | null {
  try {
    const data = JSON.parse(storage.getItem(sessionKey) || 'null')
    if (
      data &&
      typeof data.accessToken === 'string' &&
      typeof data.refreshToken === 'string' &&
      Number.isFinite(data.expiresAt)
    )
      return data
  } catch {
    /* corrupt storage is a signed-out session */
  }
  storage.removeItem(sessionKey)
  return null
}

export function clearSession(storage: Storage = sessionStorage): void {
  storage.removeItem(sessionKey)
  storage.removeItem(pendingKey)
}

async function cognito(
  config: AuthConfig,
  action: string,
  body: object,
): Promise<Response> {
  return fetch(config.apiUrl, {
    method: 'POST',
    credentials: 'omit',
    cache: 'no-store',
    redirect: 'error',
    headers: {
      'Content-Type': 'application/x-amz-json-1.1',
      'X-Amz-Target': `AWSCognitoIdentityProviderService.${action}`,
    },
    body: JSON.stringify(body),
    signal: AbortSignal.timeout(15000),
  })
}

const refreshes = new WeakMap<Storage, Promise<Session>>()

export function refreshSession(
  config: AuthConfig,
  session: Session,
  storage: Storage = sessionStorage,
): Promise<Session> {
  const existing = refreshes.get(storage)
  if (existing) return existing
  const pending = performRefresh(config, session, storage).finally(() => {
    refreshes.delete(storage)
  })
  refreshes.set(storage, pending)
  return pending
}

async function performRefresh(
  config: AuthConfig,
  session: Session,
  storage: Storage,
): Promise<Session> {
  const previous = storage.getItem(sessionKey)
  const response = await cognito(config, 'InitiateAuth', {
    AuthFlow: 'REFRESH_TOKEN_AUTH',
    ClientId: config.clientId,
    AuthParameters: { REFRESH_TOKEN: session.refreshToken },
  })
  if (!response.ok)
    throw new Error('Your session expired. Please sign in again.')
  const data = (await response.json()).AuthenticationResult
  const refreshed = validateSession(
    config,
    data?.AccessToken,
    data?.RefreshToken || session.refreshToken,
    data?.ExpiresIn,
  )
  if (storage.getItem(sessionKey) !== previous)
    throw new Error('Session changed during refresh.')
  storage.setItem(sessionKey, JSON.stringify(refreshed))
  return refreshed
}

export async function endSession(
  config: AuthConfig,
  session: Session | null,
  storage: Storage = sessionStorage,
): Promise<string> {
  clearSession(storage)
  let revoked = true
  try {
    if (session)
      revoked = (
        await cognito(config, 'RevokeToken', {
          ClientId: config.clientId,
          Token: session.refreshToken,
        })
      ).ok
  } catch {
    revoked = false
  }
  // Clear local credentials even if revocation is unavailable; still end hosted login.
  if (!revoked)
    storage.setItem(
      'telelink.logout-warning',
      'Signed out locally. Token revocation could not be confirmed.',
    )
  const url = new URL(config.logoutUrl)
  url.search = new URLSearchParams({
    client_id: config.clientId,
    logout_uri: config.logoutUri,
  }).toString()
  return url.toString()
}
