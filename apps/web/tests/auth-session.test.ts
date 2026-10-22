import assert from 'node:assert/strict'
import { test } from 'node:test'
import {
  beginLogin,
  clearSession,
  endSession,
  finishLogin,
  pkceChallenge,
  readSession,
  refreshSession,
  signInWithPassword,
} from '../src/auth/session'
import type { AuthConfig } from '../src/auth/session'

class MemoryStorage implements Storage {
  data = new Map<string, string>()
  get length() {
    return this.data.size
  }
  clear() {
    this.data.clear()
  }
  getItem(key: string) {
    return this.data.get(key) ?? null
  }
  key(index: number) {
    return [...this.data.keys()][index] ?? null
  }
  removeItem(key: string) {
    this.data.delete(key)
  }
  setItem(key: string, value: string) {
    this.data.set(key, value)
  }
}

const config: AuthConfig = {
  clientId: 'web',
  issuer: 'http://localhost:4566/pool',
  authorizeUrl: 'http://localhost:4566/cognito-idp/oauth2/authorize',
  tokenUrl: 'http://localhost:4566/cognito-idp/oauth2/token',
  logoutUrl: 'http://localhost:4566/cognito-idp/logout',
  apiUrl: 'http://localhost:4566/',
  redirectUri: 'http://localhost:5173/auth/callback',
  logoutUri: 'http://localhost:5173/',
}

function accessToken() {
  const claims = {
    iss: config.issuer,
    client_id: 'web',
    token_use: 'access',
    exp: Math.floor(Date.now() / 1000) + 300,
  }
  return `header.${Buffer.from(JSON.stringify(claims)).toString('base64url')}.signature`
}

function refreshResponse() {
  return Response.json({
    AuthenticationResult: { AccessToken: accessToken(), ExpiresIn: 300 },
  })
}

test('password sign-in uses the configured public client and stores only validated tokens', async (t) => {
  const storage = new MemoryStorage()
  t.mock.method(
    globalThis,
    'fetch',
    async (url: RequestInfo | URL, init?: RequestInit) => {
      assert.equal(url, config.apiUrl)
      assert.equal(init?.credentials, 'omit')
      assert.equal(init?.redirect, 'error')
      assert.deepEqual(JSON.parse(init?.body as string), {
        AuthFlow: 'USER_PASSWORD_AUTH',
        ClientId: 'web',
        AuthParameters: {
          USERNAME: 'patient@example.test',
          PASSWORD: 'test-password',
        },
      })
      return Response.json({
        AuthenticationResult: {
          AccessToken: accessToken(),
          RefreshToken: 'refresh',
          ExpiresIn: 300,
        },
      })
    },
  )
  await signInWithPassword(
    config,
    ' patient@example.test ',
    'test-password',
    storage,
  )
  assert.equal(readSession(storage)?.refreshToken, 'refresh')
  assert.equal(storage.length, 1)
  assert.doesNotMatch(
    storage.getItem('telelink.session')!,
    /test-password|patient@example/,
  )
})

test('invalid credentials, challenges and malformed tokens cannot create a password session', async (t) => {
  const storage = new MemoryStorage()
  const request = t.mock.method(
    globalThis,
    'fetch',
    async () => new Response('NotAuthorized', { status: 400 }),
  )
  await assert.rejects(
    signInWithPassword(config, 'patient@example.test', 'wrong', storage),
    /Check your email and password/,
  )
  assert.equal(readSession(storage), null)
  request.mock.mockImplementation(async () =>
    Response.json({
      ChallengeName: 'SOFTWARE_TOKEN_MFA',
      Session: 'challenge-session',
    }),
  )
  await assert.rejects(
    signInWithPassword(config, 'patient@example.test', 'test', storage),
    /additional sign-in step/,
  )
  assert.equal(readSession(storage), null)
  request.mock.mockImplementation(async () =>
    Response.json({
      AuthenticationResult: {
        AccessToken: 'malformed',
        RefreshToken: 'refresh',
        ExpiresIn: 300,
      },
    }),
  )
  await assert.rejects(
    signInWithPassword(config, 'patient@example.test', 'test', storage),
    /could not be completed/,
  )
  assert.equal(readSession(storage), null)
  request.mock.mockImplementation(async () => Response.json(null))
  await assert.rejects(
    signInWithPassword(config, 'patient@example.test', 'test', storage),
    /could not be completed/,
  )
  assert.equal(readSession(storage), null)
})

test('RFC 7636 S256 vector and public-client authorization', async () => {
  assert.equal(
    await pkceChallenge('dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk'),
    'E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM',
  )
  const storage = new MemoryStorage()
  const url = new URL(await beginLogin(config, storage))
  const params = url.searchParams
  const pending = JSON.parse(storage.getItem('telelink.pkce')!)
  assert.equal(params.get('code_challenge_method'), 'S256')
  assert.equal(params.get('response_type'), 'code')
  assert.equal(params.get('redirect_uri'), config.redirectUri)
  assert.ok(!params.has('client_secret'))
  assert.equal(
    params.get('code_challenge'),
    await pkceChallenge(pending.verifier),
  )
})

test('callback rejects wrong state and replay before exchange', async () => {
  const storage = new MemoryStorage()
  await beginLogin(config, storage)
  await assert.rejects(
    finishLogin(config, '?code=secret&state=wrong', storage),
    /state/,
  )
  await assert.rejects(
    finishLogin(config, '?code=secret&state=wrong', storage),
    /state/,
  )
})

test('callback, refresh and logout with revocation outage', async (t) => {
  const storage = new MemoryStorage()
  const url = new URL(await beginLogin(config, storage))
  const fetch = t.mock.method(
    globalThis,
    'fetch',
    async (_url: RequestInfo | URL, init?: RequestInit) => {
      const body = new URLSearchParams(init?.body as URLSearchParams)
      assert.equal(body.get('grant_type'), 'authorization_code')
      assert.equal(init?.credentials, 'omit')
      return Response.json({
        access_token: accessToken(),
        refresh_token: 'refresh',
        expires_in: 300,
      })
    },
  )
  const session = await finishLogin(
    config,
    `?code=secret&state=${url.searchParams.get('state')}`,
    storage,
  )
  assert.equal(readSession(storage)?.refreshToken, 'refresh')

  fetch.mock.mockImplementation(
    async (_url: RequestInfo | URL, init?: RequestInit) => {
      assert.equal(
        JSON.parse(init?.body as string).AuthFlow,
        'REFRESH_TOKEN_AUTH',
      )
      return refreshResponse()
    },
  )
  assert.equal(
    (await refreshSession(config, session, storage)).refreshToken,
    'refresh',
  )

  fetch.mock.mockImplementation(async () => {
    throw new Error('offline')
  })
  const logout = new URL(await endSession(config, session, storage))
  assert.equal(logout.searchParams.get('logout_uri'), config.logoutUri)
  assert.equal(readSession(storage), null)
  assert.ok(storage.getItem('telelink.logout-warning'))
})

test('expired callback and failed refresh reject renewal', async (t) => {
  const storage = new MemoryStorage()
  storage.setItem(
    'telelink.pkce',
    JSON.stringify({
      verifier: 'v',
      state: 's',
      createdAt: Date.now() - 660000,
    }),
  )
  await assert.rejects(
    finishLogin(config, '?code=c&state=s', storage),
    /expired/,
  )
  t.mock.method(
    globalThis,
    'fetch',
    async () => new Response('', { status: 400 }),
  )
  const session = { accessToken: 'old', refreshToken: 'bad', expiresAt: 0 }
  storage.setItem('telelink.session', JSON.stringify(session))
  await assert.rejects(refreshSession(config, session, storage), /expired/)
  assert.equal(readSession(storage)?.accessToken, 'old')
})

test('shared refresh cannot restore a logged-out session', async (t) => {
  const storage = new MemoryStorage()
  const session = {
    accessToken: accessToken(),
    refreshToken: 'refresh',
    expiresAt: Date.now(),
  }
  storage.setItem('telelink.session', JSON.stringify(session))
  let complete!: (response: Response) => void
  const fetch = t.mock.method(
    globalThis,
    'fetch',
    () =>
      new Promise<Response>((resolve) => {
        complete = resolve
      }),
  )
  const first = refreshSession(config, session, storage)
  const second = refreshSession(config, session, storage)
  assert.equal(first, second)
  assert.equal(fetch.mock.callCount(), 1)
  clearSession(storage)
  complete(refreshResponse())
  await assert.rejects(first, /Session changed/)
  assert.equal(readSession(storage), null)
  await assert.rejects(
    refreshSession(config, session, storage),
    /Session changed/,
  )
  assert.equal(fetch.mock.callCount(), 1)
})
