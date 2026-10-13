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

function accessToken(overrides = {}) {
  return `header.${Buffer.from(JSON.stringify({ iss: config.issuer, client_id: 'web', token_use: 'access', exp: Math.floor(Date.now() / 1000) + 300, ...overrides })).toString('base64url')}.signature`
}

test('RFC 7636 S256 vector and random public-client authorization', async () => {
  assert.equal(
    await pkceChallenge('dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk'),
    'E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM',
  )
  const storage = new MemoryStorage()
  const url = new URL(await beginLogin(config, storage))
  assert.equal(url.searchParams.get('code_challenge_method'), 'S256')
  assert.equal(url.searchParams.get('response_type'), 'code')
  assert.equal(url.searchParams.get('redirect_uri'), config.redirectUri)
  assert.ok(!url.searchParams.has('client_secret'))
  const pending = JSON.parse(storage.getItem('telelink.pkce')!)
  assert.equal(
    url.searchParams.get('code_challenge'),
    await pkceChallenge(pending.verifier),
  )
})

test('callback rejects wrong state and replay before any exchange', async () => {
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

test('callback exchange, refresh and logout clear credentials despite revocation outage', async () => {
  const original = globalThis.fetch
  const storage = new MemoryStorage()
  try {
    const url = new URL(await beginLogin(config, storage))
    globalThis.fetch = async (_url, init) => {
      assert.equal(
        new URLSearchParams(init?.body as URLSearchParams).get('grant_type'),
        'authorization_code',
      )
      assert.equal(init?.credentials, 'omit')
      return Response.json({
        access_token: accessToken(),
        refresh_token: 'refresh-secret',
        expires_in: 300,
      })
    }
    const session = await finishLogin(
      config,
      `?code=secret&state=${url.searchParams.get('state')}`,
      storage,
    )
    assert.equal(readSession(storage)?.refreshToken, 'refresh-secret')
    globalThis.fetch = async (_url, init) => {
      assert.equal(
        JSON.parse(init?.body as string).AuthFlow,
        'REFRESH_TOKEN_AUTH',
      )
      return Response.json({
        AuthenticationResult: { AccessToken: accessToken(), ExpiresIn: 300 },
      })
    }
    assert.equal(
      (await refreshSession(config, session, storage)).refreshToken,
      'refresh-secret',
    )
    globalThis.fetch = async () => {
      throw new Error('offline')
    }
    assert.equal(
      new URL(await endSession(config, session, storage)).searchParams.get(
        'logout_uri',
      ),
      config.logoutUri,
    )
    assert.equal(readSession(storage), null)
    assert.ok(storage.getItem('telelink.logout-warning'))
    clearSession(storage)
  } finally {
    globalThis.fetch = original
  }
})

test('expired callback and failed refresh cannot create a session', async () => {
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
  const original = globalThis.fetch
  try {
    globalThis.fetch = async () => new Response('', { status: 400 })
    await assert.rejects(
      refreshSession(
        config,
        { accessToken: 'old', refreshToken: 'bad', expiresAt: 0 },
        storage,
      ),
      /expired/,
    )
    assert.equal(readSession(storage), null)
  } finally {
    globalThis.fetch = original
  }
})

test('concurrent refresh is shared and cannot restore a logged-out session', async () => {
  const storage = new MemoryStorage()
  const session = {
    accessToken: accessToken(),
    refreshToken: 'refresh',
    expiresAt: Date.now(),
  }
  storage.setItem('telelink.session', JSON.stringify(session))
  const original = globalThis.fetch
  let complete!: (response: Response) => void
  let requests = 0
  try {
    globalThis.fetch = async () => {
      requests++
      return new Promise<Response>((resolve) => {
        complete = resolve
      })
    }
    const first = refreshSession(config, session, storage)
    const second = refreshSession(config, session, storage)
    assert.equal(first, second)
    assert.equal(requests, 1)
    clearSession(storage)
    complete(
      Response.json({
        AuthenticationResult: { AccessToken: accessToken(), ExpiresIn: 300 },
      }),
    )
    await assert.rejects(first, /Session changed/)
    assert.equal(readSession(storage), null)
  } finally {
    globalThis.fetch = original
  }
})
