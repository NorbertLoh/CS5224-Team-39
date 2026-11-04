// Focused RF15 checks with independent tab modules and shared browser storage.
// Run after npm ci in apps/web: node dev/check_auth_session.mjs
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import vm from 'node:vm'
import ts from '../apps/web/node_modules/typescript/lib/typescript.js'

const source = readFileSync(new URL('../apps/web/src/auth/session.ts', import.meta.url), 'utf8')
const code = ts.transpileModule(source.replace('import.meta.env', '{}'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
}).outputText
const values = new Map()
const tabs = []
let queue = Promise.resolve()
const locks = {
  request: (_name, action) => {
    const result = queue.then(action)
    queue = result.catch(() => {})
    return result
  },
}
let requests = 0
let respond
const config = { clientId: 'test', issuer: 'https://issuer.test', apiUrl: 'https://issuer.test/api' }
const token = () => `header.${Buffer.from(JSON.stringify({
  iss: config.issuer, client_id: config.clientId, token_use: 'access',
  exp: Math.floor(Date.now() / 1000) + 3600,
})).toString('base64url')}.signature`
const response = () => ({ ok: true, json: async () => ({
  AuthenticationResult: { AccessToken: token(), RefreshToken: 'refresh-a', ExpiresIn: 3600 },
}) })

function tab() {
  const window = new EventTarget()
  const privateValues = new Map()
  const sessionStorage = {
    getItem: (key) => privateValues.get(key) ?? null,
    setItem: (key, value) => privateValues.set(key, value),
    removeItem: (key) => privateValues.delete(key),
  }
  const notify = (key) => {
    for (const other of tabs) {
      if (other.window === window) continue
      other.window.dispatchEvent(Object.assign(new Event('storage'), {
        key, storageArea: other.localStorage,
      }))
    }
  }
  const localStorage = {
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => { values.set(key, value); notify(key) },
    removeItem: (key) => { values.delete(key); notify(key) },
    clear: () => { values.clear(); notify(null) },
  }
  const context = {
    exports: {}, require: () => ({ usesAws: () => false }),
    window, localStorage, sessionStorage, navigator: { locks },
    Event, URL, URLSearchParams, AbortSignal, crypto: globalThis.crypto,
    TextEncoder, TextDecoder, atob, btoa,
    fetch: async () => { requests++; return respond() },
  }
  vm.runInNewContext(code, context)
  const result = { ...context.exports, window, localStorage, sessionStorage }
  tabs.push(result)
  return result
}

const first = tab()
respond = response
await first.signInWithPassword(config, 'patient@example.test', 'test-password')
const second = tab()
assert.equal(second.readSession().accessToken, first.readSession().accessToken)
assert.equal(first.sessionStorage.getItem('telelink.session'), null)
console.log('PASS: a fresh tab reuses the shared sign-in')

const pkceConfig = { ...config, authorizeUrl: 'https://issuer.test/authorize', redirectUri: 'https://app.test/auth/callback' }
await first.beginLogin(pkceConfig)
assert.ok(first.sessionStorage.getItem('telelink.pkce'))
assert.equal(second.sessionStorage.getItem('telelink.pkce'), null)
assert.equal(values.has('telelink.pkce'), false)
await assert.rejects(second.finishLogin(pkceConfig, '?code=test&state=wrong'), /state did not match/)
const pending = JSON.parse(first.sessionStorage.getItem('telelink.pkce'))
respond = () => ({ ok: true, json: async () => ({ access_token: token(), refresh_token: 'refresh-a', expires_in: 3600 }) })
await first.finishLogin(pkceConfig, `?code=test&state=${pending.state}`)
assert.equal(first.sessionStorage.getItem('telelink.pkce'), null)
assert.equal(second.readSession().refreshToken, 'refresh-a')
respond = response
console.log('PASS: PKCE transactions stay tab-local and callbacks save the shared session')

let notifications = 0
const unsubscribe = second.subscribeToSession(() => { notifications++ })
first.clearSession()
assert.equal(second.readSession(), null)
assert.equal(notifications, 2) // Subscription snapshot and remote logout.
await first.signInWithPassword(config, 'other@example.test', 'test-password')
assert.equal(notifications, 3)
second.clearSession()
assert.equal(notifications, 4) // Same-document notification.
unsubscribe()
console.log('PASS: logout and sign-in notify existing tabs and the current document')

await first.signInWithPassword(config, 'patient@example.test', 'test-password')
second.localStorage.clear()
assert.equal(first.readSession(), null)
console.log('PASS: clearing shared browser storage removes the session')

const expire = () => {
  const session = { accessToken: 'expired', refreshToken: 'refresh-a', expiresAt: Date.now() - 1 }
  first.localStorage.setItem('telelink.session', JSON.stringify(session))
  return session
}
let old = expire()
const before = requests
const [renewedA, renewedB] = await Promise.all([
  first.refreshSession(config, old), second.refreshSession(config, old),
])
assert.equal(requests, before + 1)
assert.equal(renewedA.accessToken, renewedB.accessToken)
console.log('PASS: concurrent tabs issue one refresh and reuse the renewed token')

for (const change of ['logout', 'account']) {
  old = expire()
  let release
  let started
  const sent = new Promise((resolve) => { started = resolve })
  respond = () => { started(); return new Promise((resolve) => { release = resolve }) }
  const refreshing = first.refreshSession(config, old)
  await sent
  second.clearSession()
  if (change === 'account') {
    second.localStorage.setItem('telelink.session', JSON.stringify({
      accessToken: 'other-account', refreshToken: 'refresh-b', expiresAt: Date.now() + 3600000,
    }))
  }
  release(response())
  await assert.rejects(refreshing, /Session changed during refresh/)
  assert.equal(first.readSession()?.accessToken ?? null, change === 'logout' ? null : 'other-account')
}
console.log('PASS: late refreshes cannot undo logout or overwrite another account')

respond = () => { throw new Error('offline') }
old = expire()
await assert.rejects(first.refreshSession(config, old), /session expired/i)
respond = response
assert.ok((await first.refreshSession(config, old)).expiresAt > Date.now())
console.log('PASS: refresh failure releases the lock and allows retry')
