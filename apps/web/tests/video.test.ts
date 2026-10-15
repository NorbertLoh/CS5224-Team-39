import assert from 'node:assert/strict'
import { test } from 'node:test'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { VideoRoom } from '../src/features/video/VideoRoom'
import { mediaError } from '../src/features/video/useLocalMedia'
import { canAccess, parseRoute } from '../src/navigation/access'
import type { Identity } from '../src/features/clinics/api'

test('patient call markup excludes the doctor workspace and clinical fixture identifiers', () => {
  const patient = renderToStaticMarkup(
    createElement(VideoRoom, { role: 'patient' }),
  )
  const doctor = renderToStaticMarkup(
    createElement(VideoRoom, { role: 'doctor' }),
  )
  assert.match(patient, /Your video consultation/)
  assert.match(patient, /Waiting for your doctor/)
  assert.doesNotMatch(
    patient,
    /Doctor workspace|Consultation notes and prescription|00000000-0000-4000/,
  )
  assert.match(doctor, /Doctor workspace/)
  assert.match(doctor, /Consultation notes and prescription/)
  assert.match(doctor, /Waiting for your patient/)
})

test('consultation routes enforce role authorization instead of trusting a URL', () => {
  const patient: Identity = {
    subject_id: 'patient',
    global_roles: ['patient'],
    memberships: [],
  }
  const doctor: Identity = {
    subject_id: 'doctor',
    global_roles: [],
    memberships: [{ tenant_id: 'clinic', roles: ['doctor'], status: 'active' }],
  }
  const doctorRoute = parseRoute('/doctor/consultation')
  const patientRoute = parseRoute('/patient/consultation')
  assert.deepEqual(doctorRoute, { kind: 'consultation', role: 'doctor' })
  assert.deepEqual(patientRoute, { kind: 'consultation', role: 'patient' })
  assert.equal(canAccess(patient, doctorRoute), false)
  assert.equal(canAccess(doctor, patientRoute), false)
  assert.equal(canAccess(patient, patientRoute), true)
  assert.equal(canAccess(doctor, doctorRoute), true)
  assert.equal(canAccess({ ...doctor, memberships: [] }, doctorRoute), false)
  assert.deepEqual(parseRoute('/clinic-admin/consultation'), {
    kind: 'missing',
  })
})

test('device errors give actionable guidance without exposing raw exceptions', () => {
  assert.match(
    mediaError(new DOMException('private details', 'NotAllowedError')),
    /permission was denied/,
  )
  assert.match(
    mediaError(new DOMException('', 'NotFoundError')),
    /No camera or microphone/,
  )
  assert.match(mediaError(new DOMException('', 'NotReadableError')), /busy/)
  assert.doesNotMatch(
    mediaError(new Error('private details')),
    /private details/,
  )
})
