import assert from 'node:assert/strict'
import { test } from 'node:test'
import { readDemoProfile, saveDemoProfile } from '../src/features/clinic-profile/demo-storage'
import { storefrontClinics } from '../src/features/storefront/fixtures'

function storage() {
  const values = new Map<string, string>()
  return { getItem: (key: string) => values.get(key) ?? null, setItem: (key: string, value: string) => { values.set(key, value) } }
}

test('demo saves restore edited fields and image preview after reopening', () => {
  const browser = storage()
  const clinic = storefrontClinics[0]
  const edited = { ...clinic, name: 'Saved demo clinic', branding: { ...clinic.branding, primary_color: '#123456' } }
  const preview = 'data:image/png;base64,aGVsbG8='
  saveDemoProfile(clinic.tenant_id, edited, preview, browser)
  const restored = readDemoProfile(clinic.tenant_id, clinic, browser)
  assert.equal(restored.profile.name, 'Saved demo clinic')
  assert.equal(restored.profile.branding.primary_color, '#123456')
  assert.equal(restored.logoPreview, preview)
  assert.deepEqual(Object.keys(restored.profile).sort(), ['branding', 'consultation_price', 'name'])
})

test('saved demo data stays within its clinic and removal replaces the saved image', () => {
  const browser = storage()
  const [a, b] = storefrontClinics
  saveDemoProfile(a.tenant_id, { ...a, name: 'Edited A' }, 'data:image/png;base64,aA==', browser)
  assert.equal(readDemoProfile(b.tenant_id, b, browser).profile.name, b.name)
  saveDemoProfile(a.tenant_id, { ...a, name: 'Edited A' }, null, browser)
  assert.equal(readDemoProfile(a.tenant_id, a, browser).logoPreview, null)
})

test('corrupt and unavailable browser storage falls back to the agreed clinic fixture', () => {
  const clinic = storefrontClinics[0]
  for (const contents of ['not JSON', '{"profile":{"name":"invalid"}}']) {
    const browser = { getItem: () => contents, setItem: () => {} }
    assert.equal(readDemoProfile(clinic.tenant_id, clinic, browser).profile, clinic)
  }
  const blocked = { getItem: (): string | null => { throw new Error('Blocked') }, setItem: () => {} }
  assert.equal(readDemoProfile(clinic.tenant_id, clinic, blocked).profile, clinic)
})

test('write failures propagate so the editor cannot report a false successful save', () => {
  const clinic = storefrontClinics[0]
  const full = { getItem: () => null, setItem: () => { throw new Error('Quota exceeded') } }
  assert.throws(() => saveDemoProfile(clinic.tenant_id, clinic, null, full), /Quota exceeded/)
})
