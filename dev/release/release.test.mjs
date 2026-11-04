import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { images, buildArgs, frontendConfig, platformOutput, root } from './release.mjs'

test('release inventory covers every Terraform workload and migration image', () => {
  const catalog = readFileSync(resolve(root, 'infra/modules/demo-platform/catalog.tf'), 'utf8')
  const services = catalog.match(/services\s+= toset\(\[(.*?)\]\)/)[1].match(/"([a-z_]+)"/g).map(value => JSON.parse(value))
  assert.deepEqual(images.map(image => image.name).sort(), [...services, 'notification', 'signalling', 'document-lambda', 'notification-lambda'].sort())
  for (const image of images) {
    assert.equal(image.platform, image.name.endsWith('-lambda') ? 'linux/amd64' : 'linux/arm64')
    const dockerfile = readFileSync(resolve(root, image.context, image.file), 'utf8')
    assert.ok(dockerfile.includes('FROM '))
    const args = buildArgs(image, 'telelink-release/check:revision')
    assert.ok(args.includes('--load'))
    assert.ok(args.includes('--provenance=false'))
    assert.ok(!args.includes('--push'))
    assert.equal(args.includes('--build-context'), !!image.shared)
  }
})

test('frontend rejects missing settings, local endpoints and accidental secrets', () => {
  const config = JSON.parse(readFileSync(resolve(root, 'dev/release/frontend.check.json'), 'utf8'))
  assert.deepEqual(frontendConfig(config), config)
  assert.throws(() => frontendConfig({ ...config, VITE_USE_AWS: 'false' }))
  assert.throws(() => frontendConfig({ ...config, SERVICE_SECRET: 'private' }))
  assert.throws(() => frontendConfig({ ...config, VITE_AWS_COGNITO_CLIENT_ID: '' }))
  for (const url of ['http://localhost:8000', 'https://user:password@example.org', 'https://example.org?token=secret']) {
    assert.throws(() => frontendConfig({ ...config, VITE_AWS_API_BASE_URL: url }))
  }
})

test('both Terraform roots and direct output values are accepted', () => {
  const value = { repositories: {}, frontend_environment: {} }
  assert.equal(platformOutput({ platform: { value } }), value)
  assert.equal(platformOutput({ demo: { value } }), value)
  assert.equal(platformOutput(value), value)
  assert.throws(() => platformOutput({}))
})
