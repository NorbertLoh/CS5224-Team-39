import assert from 'node:assert/strict'
import { test } from 'node:test'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { canAccess, clinicIds, hasRole, parseRoute } from '../src/navigation/access'
import { RoleNavigation } from '../src/navigation/RoleNavigation'
import type { Identity } from '../src/features/clinics/api'

const clinicA = '11111111-1111-4111-8111-111111111111'
const clinicB = '22222222-2222-4222-8222-222222222222'
const identity: Identity = {
  subject_id: 'subject', global_roles: ['patient'],
  memberships: [
    { tenant_id: clinicA, roles: ['doctor', 'clinic_admin'], status: 'active' },
    { tenant_id: clinicB, roles: ['clinic_admin'], status: 'revoked' },
  ],
}

test('only current active memberships grant clinic roles and selection', () => {
  assert.deepEqual(clinicIds(identity, 'clinic_admin'), [clinicA])
  assert.equal(hasRole(identity, 'patient'), true)
  assert.equal(hasRole(identity, 'doctor'), true)
  assert.equal(hasRole(identity, 'platform_admin'), false)
  assert.equal(canAccess(identity, parseRoute(`/clinic-admin/clinics/${clinicA}/staff`)), true)
  assert.equal(canAccess(identity, parseRoute(`/clinic-admin/clinics/${clinicB}/staff`)), false)
  assert.equal(canAccess(identity, parseRoute(`/doctor/clinics/${clinicB}`)), false)
  assert.equal(canAccess({ ...identity, memberships: [] }, parseRoute(`/doctor/clinics/${clinicA}`)), false)
})

test('doctor membership cannot grant clinic administration or global roles', () => {
  const doctor: Identity = { ...identity, global_roles: [], memberships: [{ tenant_id: clinicA, roles: ['doctor'], status: 'active' }] }
  assert.equal(canAccess(doctor, parseRoute('/doctor')), true)
  assert.equal(canAccess(doctor, parseRoute(`/clinic-admin/clinics/${clinicA}/profile`)), false)
  assert.equal(canAccess(doctor, parseRoute('/patient')), false)
  assert.equal(canAccess(doctor, parseRoute('/platform-admin/clinics')), false)
})

test('multiple active clinics stay role-specific and duplicates do not create extra choices', () => {
  const multi: Identity = { ...identity, memberships: [
    ...identity.memberships,
    { tenant_id: clinicB, roles: ['doctor'], status: 'active' },
    { tenant_id: clinicA, roles: ['doctor'], status: 'active' },
  ] }
  assert.deepEqual(clinicIds(multi, 'doctor'), [clinicA, clinicB])
  assert.deepEqual(clinicIds(multi, 'clinic_admin'), [clinicA])
  assert.equal(canAccess(multi, parseRoute(`/doctor/clinics/${clinicB}`)), true)
  assert.equal(canAccess(multi, parseRoute(`/clinic-admin/clinics/${clinicB}/staff`)), false)
})

test('platform administration follows tenant API access without granting doctor access', () => {
  const platform = { ...identity, global_roles: ['platform_admin'], memberships: [] }
  assert.equal(canAccess(platform, parseRoute('/platform-admin/clinics')), true)
  assert.equal(canAccess(platform, parseRoute(`/clinic-admin/clinics/${clinicB}/profile`)), true)
  assert.equal(canAccess(platform, parseRoute(`/doctor/clinics/${clinicA}`)), false)
})

test('unknown and malformed paths do not fall through to an editor or homepage', () => {
  for (const path of ['/clinic-admin/wrong', '/clinic-admin/clinics/arbitrary/profile', '/platform-admin/clinics/bad-id', '/doctor/clinics/bad-id', '/patient/wrong', '/unknown']) {
    assert.deepEqual(parseRoute(path), { kind: 'missing' })
  }
  assert.deepEqual(parseRoute('/doctor/'), { kind: 'role', role: 'doctor' })
  assert.deepEqual(parseRoute('/auth/callback'), { kind: 'home' })
  assert.deepEqual(parseRoute('/clinics/clinic-a'), { kind: 'storefront', slug: 'clinic-a' })
})

test('navigation renders only granted roles and selectable clinics', () => {
  const markup = renderToStaticMarkup(createElement(RoleNavigation, { identity, route: parseRoute(`/clinic-admin/clinics/${clinicA}/staff`) }))
  assert.match(markup, /href="\/patient"/)
  assert.match(markup, /href="\/doctor"/)
  assert.match(markup, /aria-current="page"/)
  assert.match(markup, new RegExp(`value="${clinicA}" selected=""`))
  assert.doesNotMatch(markup, /platform-admin/)
  assert.doesNotMatch(markup, new RegExp(clinicB))
  const stale = renderToStaticMarkup(createElement(RoleNavigation, { identity, route: parseRoute(`/clinic-admin/clinics/${clinicB}/staff`) }))
  assert.match(stale, /value="" disabled="" selected=""/)
})
