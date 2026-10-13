import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'
import { findClinic, storefrontClinics } from '../src/features/storefront/fixtures'

const shared = JSON.parse(readFileSync(new URL('../../../dev/fixtures/telelink.json', import.meta.url), 'utf8')) as {
  clinics: Array<{ tenant_id: string; slug: string; name: string; status: string; branding: object; consultation_price: object }>
  memberships: Array<{ subject_id: string; tenant_id: string; roles: string[]; status: string }>
  subjects: Array<{ subject_id: string; display_name: string }>
}

test('public storefront fixtures match agreed clinic data and only current clinic doctors', () => {
  assert.equal(storefrontClinics.length, shared.clinics.filter(clinic => clinic.status === 'active').length)
  for (const clinic of storefrontClinics) {
    const source = shared.clinics.find(item => item.tenant_id === clinic.tenant_id)!
    const doctors = shared.memberships
      .filter(member => member.tenant_id === clinic.tenant_id && member.status === 'active' && member.roles.includes('doctor'))
      .map(member => {
        const subject = shared.subjects.find(item => item.subject_id === member.subject_id)!
        return { doctor_id: subject.subject_id, display_name: subject.display_name }
      })
      .sort((a, b) => a.display_name.localeCompare(b.display_name) || a.doctor_id.localeCompare(b.doctor_id))
    assert.deepEqual(clinic, {
      tenant_id: source.tenant_id, slug: source.slug, name: source.name, status: source.status,
      branding: source.branding, consultation_price: source.consultation_price, doctors,
    })
  }
})

test('public preview does not bundle private identity, membership or clinical fixture fields', () => {
  const publicJson = JSON.stringify(storefrontClinics)
  for (const field of ['cognito_sub', 'membership_id', 'subject_id', 'global_roles', 'commission_bps', 'review_reason', 'patient_id', 'prescriptions', 'appointments']) {
    assert.ok(!publicJson.includes(`"${field}"`), `Public fixture contains ${field}`)
  }
})

test('public clinic lookup conceals unknown and inactive clinics', () => {
  assert.equal(findClinic('unknown-clinic'), undefined)
  for (const status of ['pending_review', 'rejected', 'suspended']) {
    const inactive = { ...storefrontClinics[0], status }
    assert.equal(findClinic(inactive.slug, [inactive]), undefined)
  }
})
