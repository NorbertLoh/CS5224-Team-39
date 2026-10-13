import assert from 'node:assert/strict'
import { test } from 'node:test'
import { authConfig } from '../src/auth/session'
import { apiBaseUrl, usesAws } from '../src/lib/backend-config'

test('flag selects local or AWS endpoints without fixture fallback', () => {
  const settings = { VITE_LOCAL_API_BASE_URL: '/api/v1', VITE_AWS_API_BASE_URL: 'https://api.example.com/api/v1/' }
  assert.equal(usesAws({}), false)
  assert.equal(apiBaseUrl({ ...settings, VITE_USE_AWS: 'false' }), '/api/v1')
  assert.equal(apiBaseUrl({ ...settings, VITE_USE_AWS: 'true' }), 'https://api.example.com/api/v1')
  assert.throws(() => usesAws({ VITE_USE_AWS: 'demo' }))
  assert.throws(() => apiBaseUrl({ VITE_USE_AWS: 'true' }))
  for (const url of ['/api/v1', 'http://localhost:8000', 'https://user:password@api.example.com', 'https://api.example.com/?key=value']) {
    assert.throws(() => apiBaseUrl({ VITE_USE_AWS: 'true', VITE_AWS_API_BASE_URL: url }))
  }
})


test('flag also selects matching Cognito settings for local builds and AWS', () => {
  const local = { VITE_COGNITO_CLIENT_ID: 'local-client', VITE_COGNITO_ISSUER: 'http://localhost:4566/local-pool', VITE_COGNITO_OAUTH_BASE_URL: 'http://localhost:4566/cognito-idp', VITE_COGNITO_API_URL: 'http://localhost:4566/' }
  const aws = { VITE_AWS_COGNITO_CLIENT_ID: 'aws-client', VITE_AWS_COGNITO_ISSUER: 'https://cognito-idp.ap-southeast-1.amazonaws.com/pool', VITE_AWS_COGNITO_OAUTH_BASE_URL: 'https://auth.example.com', VITE_AWS_COGNITO_API_URL: 'https://cognito-idp.ap-southeast-1.amazonaws.com/' }
  const origin = 'http://localhost:5173'
  assert.equal(authConfig({ ...local, ...aws, VITE_USE_AWS: 'false' }, origin)?.clientId, 'local-client')
  assert.equal(authConfig({ ...local, ...aws, VITE_USE_AWS: 'true' }, origin)?.clientId, 'aws-client')
  assert.throws(() => authConfig({ ...local, VITE_USE_AWS: 'true' }, origin))
  assert.throws(() => authConfig({ ...aws, VITE_USE_AWS: 'true', VITE_AWS_COGNITO_API_URL: 'http://localhost:4566/' }, origin))
})
