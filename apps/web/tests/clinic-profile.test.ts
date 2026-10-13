import assert from 'node:assert/strict'
import { test } from 'node:test'
import { readFileSync } from 'node:fs'
import type { ClinicProfile } from '../src/features/clinic-profile/profile'
const storefrontClinics: ClinicProfile[] = JSON.parse(readFileSync(new URL('../../../dev/fixtures/telelink.json', import.meta.url), 'utf8')).clinics
import { feeMinor, profileDraft, profileUpdate, validateProfile, validLogoUrl } from '../src/features/clinic-profile/profile'
import { validateLogoFile, maxLogoBytes } from '../src/features/clinic-profile/logo-api'

test('fee input converts decimal SGD exactly without rounding or accepting exponent notation', () => {
  for (const [input, expected] of [['0', 0], ['0.01', 1], ['25.5', 2550], ['25.50', 2550], ['90071992547409.91', Number.MAX_SAFE_INTEGER]] as const) {
    assert.equal(feeMinor(input), expected)
  }
  for (const invalid of ['', '-1', '1.234', '1e2', 'NaN', 'Infinity', '90071992547409.92', '9'.repeat(1000)]) {
    assert.equal(feeMinor(invalid), null)
  }
})

test('logo permits optional HTTPS images but rejects unsafe or malformed URL input', () => {
  assert.equal(validLogoUrl('https://example.com/logo.png'), true)
  for (const invalid of ['http://example.com/logo.png', 'https:/example.com/logo.png', 'javascript:alert(1)', 'https://user:password@example.com/logo.png', 'https://example.com/a b', 'https://']) {
    assert.equal(validLogoUrl(invalid), false)
  }
  assert.equal(validateProfile({ ...profileDraft(storefrontClinics[0]), logoUrl: '' }).logoUrl, undefined)
})

test('profile validation follows name, plain-text description and six-digit colour limits', () => {
  const draft = profileDraft(storefrontClinics[0])
  assert.deepEqual(validateProfile(draft), {})
  for (const name of [' ', 'x'.repeat(201)]) assert.ok(validateProfile({ ...draft, name }).name)
  for (const description of ['<b>Clinic</b>', 'x'.repeat(2001)]) assert.ok(validateProfile({ ...draft, description }).description)
  for (const primaryColor of ['#123', 'red', '#12zz34']) assert.ok(validateProfile({ ...draft, primaryColor }).primaryColor)
  assert.deepEqual(validateProfile({ ...draft, description: '', primaryColor: '#abcdef', fee: '0' }), {})
})

test('tenant update contains only writable fields and retains exact money after a save/reset round trip', () => {
  const draft = { ...profileDraft(storefrontClinics[0]), name: '  Updated clinic  ', fee: '25.01' }
  const updated = profileUpdate(draft)
  assert.deepEqual(updated, {
    name: 'Updated clinic', branding: storefrontClinics[0].branding,
    consultation_price: { amount_minor: 2501, currency: 'SGD' },
  })
  assert.equal(profileDraft(updated).fee, '25.01')
  assert.deepEqual(Object.keys(updated).sort(), ['branding', 'consultation_price', 'name'])
})

test('editing one clinic does not mutate the other clinic or the shared fixture', () => {
  const before = JSON.stringify(storefrontClinics)
  const draft = profileDraft(storefrontClinics[0])
  draft.name = 'Updated clinic'
  draft.primaryColor = '#123456'
  assert.equal(profileUpdate(draft).name, 'Updated clinic')
  assert.equal(JSON.stringify(storefrontClinics), before)
  assert.equal(profileDraft(storefrontClinics[1]).fee, '30.00')
})

test('file picker rejects empty, oversized and unsupported uploads before contacting storage', () => {
  assert.equal(validateLogoFile(new File(['png'], 'logo.png', { type: 'image/png' })), undefined)
  assert.match(validateLogoFile(new File([], 'logo.png', { type: 'image/png' }))!, /2 MB/)
  assert.match(validateLogoFile(new File([new Uint8Array(maxLogoBytes + 1)], 'logo.png', { type: 'image/png' }))!, /2 MB/)
  assert.match(validateLogoFile(new File(['<svg/>'], 'logo.svg', { type: 'image/svg+xml' }))!, /PNG, JPEG or WebP/)
})
