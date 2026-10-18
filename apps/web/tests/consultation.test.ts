import assert from 'node:assert/strict'
import { test } from 'node:test'
import { createElement } from 'react'
import { schedulingClient, renderScheduling } from './scheduling-helpers'
import {
  bookedRoomConnection,
  roomEligibility,
  consultationAction,
} from '../src/features/video/admission'
import { LiveAppointmentDetails } from '../src/features/appointments/LiveAppointmentDetails'
import type { Appointment } from '../src/features/scheduling/api'

const now = Date.now()
const appointment: Appointment = {
  appointment_id: '83c0744b-7417-4e6a-9e7c-b196010410e2',
  tenant_id: 'clinic',
  patient_id: 'patient',
  doctor_id: 'doctor',
  slot_id: 'slot',
  starts_at: new Date(now + 600000).toISOString(),
  ends_at: new Date(now + 2400000).toISOString(),
  hold_expires_at: null,
  consultation_price: { amount_minor: 5000, currency: 'SGD' },
  status: 'confirmed',
  payment_id: 'paid',
  payment_resolution: 'confirmed',
  created_at: '',
  updated_at: '',
}

test('video links require exact participant, confirmed payment and the half-open join window', () => {
  assert.equal(roomEligibility(appointment, 'patient', 'patient', now), true)
  assert.equal(roomEligibility(appointment, 'doctor', 'doctor', now), true)
  assert.equal(roomEligibility(appointment, 'patient', 'other', now), false)
  assert.equal(
    roomEligibility(appointment, 'patient', 'patient', now - 1),
    false,
  )
  assert.equal(
    roomEligibility(appointment, 'patient', 'patient', now + 2400000),
    false,
  )
  for (const status of [
    'held',
    'pending_payment',
    'cancelled',
    'completed',
  ] as const)
    assert.equal(
      roomEligibility({ ...appointment, status }, 'patient', 'patient', now),
      false,
    )
  assert.equal(
    roomEligibility(
      { ...appointment, payment_resolution: 'refunded' },
      'patient',
      'patient',
      now,
    ),
    false,
  )
})

test('real admission and discovery adapter binds appointment/subject, fetches fresh credentials and honours cancellation', async (t) => {
  const client = schedulingClient()
  t.after(() => client.clear())
  let issues = 0
  let foreign = false
  const urls: string[] = []
  t.mock.method(globalThis, 'fetch', async (url: string, init: RequestInit) => {
    urls.push(url)
    assert.equal(init.cache, 'no-store')
    assert.equal(init.credentials, 'omit')
    assert.equal(init.redirect, 'error')
    const body = JSON.parse(init.body as string)
    if (url.endsWith('/admissions')) {
      assert.equal(
        new Headers(init.headers).get('authorization'),
        'Bearer s07-test',
      )
      assert.deepEqual(body, { appointment_id: appointment.appointment_id })
      issues++
      return Response.json({
        appointment_id: foreign ? 'another' : appointment.appointment_id,
        subject_id: 'patient',
        peer_id: `peer-${issues}`,
        token: `secret-${issues}`,
        expires_at: new Date(Date.now() + 60000).toISOString(),
        ice_servers: [],
        relay_only: false,
      })
    }
    assert.equal(new Headers(init.headers).has('authorization'), false)
    assert.deepEqual(body, { peer_id: 'peer-2', token: 'secret-2' })
    assert.equal(init.signal?.aborted, true)
    return Response.json({ peer_id: null })
  })
  const connection = bookedRoomConnection(
    appointment.appointment_id,
    'patient',
    'https://localhost:8443',
  )
  assert.equal(connection.signalling.secure, true)
  const first = await connection.acquire(new AbortController().signal)
  const second = await connection.acquire(new AbortController().signal)
  assert.notEqual(first.peerId, second.peerId)
  assert.notEqual(first.token, second.token)
  const abort = new AbortController()
  abort.abort()
  assert.equal(await connection.counterpart(second, abort.signal), null)
  foreign = true
  await assert.rejects(
    connection.acquire(new AbortController().signal),
    /context/,
  )
  assert.equal(urls[2], 'https://localhost:8443/peerjs/counterpart')
  assert.throws(
    () => bookedRoomConnection('a', 'b', 'http://localhost:5173'),
    /HTTPS/,
  )
})

test('appointment detail links only eligible participants to their booked room', () => {
  const client = schedulingClient()
  client.setQueryData(
    ['scheduling', 'appointment', 's07-test', appointment.appointment_id],
    appointment,
  )
  const render = (
    role: 'patient' | 'doctor' | 'clinic_admin',
    subjectId: string,
  ) =>
    renderScheduling(
      client,
      createElement(LiveAppointmentDetails, {
        id: appointment.appointment_id,
        token: 's07-test',
        role,
        subjectId,
        onClose() {},
      }),
    )
  assert.match(
    render('patient', 'patient'),
    new RegExp(
      `/patient/consultation\\?appointment_id=${appointment.appointment_id}`,
    ),
  )
  assert.match(render('doctor', 'doctor'), /Open video consultation/)
  assert.doesNotMatch(
    render('clinic_admin', 'admin'),
    /Open video consultation/,
  )
  assert.doesNotMatch(render('patient', 'other'), /Open video consultation/)
  client.clear()
})

test('doctor actions call the consultation service with user access, never internal service keys', async (t) => {
  const client = schedulingClient()
  t.after(() => client.clear())
  t.mock.method(globalThis, 'fetch', async (url: string, init: RequestInit) => {
    assert.equal(url, '/api/v1/consultation/appointments/appointment/start')
    assert.equal(init.method, 'POST')
    assert.equal(
      new Headers(init.headers).get('authorization'),
      'Bearer s07-test',
    )
    assert.equal(init.cache, 'no-store')
    return Response.json({
      appointment_id: 'appointment',
      status: 'in_progress',
    })
  })
  assert.equal(
    (await consultationAction('appointment', 'start')).status,
    'in_progress',
  )
})
