import assert from 'node:assert/strict'
import { test } from 'node:test'
import { createElement } from 'react'
import { schedulingClient, renderScheduling } from './scheduling-helpers'
import { ApiError } from '../src/lib/api'
import {
  createHold,
  createSlot,
  removeSlot,
  listSlots,
  listAppointments,
  appointmentDetail,
  cancelAppointment,
  canCancel,
  schedulingError,
} from '../src/features/scheduling/api'
import type { Appointment } from '../src/features/scheduling/api'
import { LiveCheckout } from '../src/features/booking/LiveCheckout'
import { LiveAppointmentDetails } from '../src/features/appointments/LiveAppointmentDetails'

const appointment: Appointment = {
  appointment_id: 'real-appointment',
  tenant_id: 'clinic',
  patient_id: 'patient',
  doctor_id: 'doctor',
  slot_id: 'slot',
  starts_at: new Date(Date.now() + 3600000).toISOString(),
  ends_at: new Date(Date.now() + 5400000).toISOString(),
  hold_expires_at: new Date(Date.now() + 600000).toISOString(),
  consultation_price: { amount_minor: 3210, currency: 'SGD' },
  status: 'held',
  payment_id: null,
  payment_resolution: 'awaiting_payment',
  created_at: '',
  updated_at: '',
}

test('scheduling writes send access tokens and only contract-owned inputs; deletion accepts 204', async (context) => {
  const client = schedulingClient()
  const calls: { url: string; init: RequestInit }[] = []
  context.mock.method(
    globalThis,
    'fetch',
    async (url: string, init: RequestInit) => {
      calls.push({ url, init })
      assert.equal(
        new Headers(init.headers).get('Authorization'),
        'Bearer s07-test',
      )
      return init.method === 'DELETE'
        ? new Response(null, { status: 204 })
        : Response.json(appointment)
    },
  )
  assert.deepEqual(await createHold('clinic', 'slot'), appointment)
  await createSlot('clinic', appointment.starts_at)
  await removeSlot('slot')
  await cancelAppointment('real-appointment', 'Changed plans')
  assert.deepEqual(JSON.parse(String(calls[0].init.body)), {
    tenant_id: 'clinic',
    slot_id: 'slot',
  })
  assert.deepEqual(JSON.parse(String(calls[1].init.body)), {
    starts_at: appointment.starts_at,
    ends_at: new Date(
      Date.parse(appointment.starts_at) + 1800000,
    ).toISOString(),
  })
  assert.deepEqual(JSON.parse(String(calls[3].init.body)), {
    reason: 'Changed plans',
  })
  assert.equal(calls[2].url, '/api/v1/scheduling/slots/slot')
  client.clear()
})

test('public slot pagination preserves filter, supports cancellation and does not send tokens', async (context) => {
  const client = schedulingClient()
  const controller = new AbortController()
  const queries: URL[] = []
  context.mock.method(
    globalThis,
    'fetch',
    async (url: string, init: RequestInit) => {
      const parsed = new URL(url, 'http://localhost')
      queries.push(parsed)
      assert.equal(new Headers(init.headers).has('Authorization'), false)
      assert.equal(init.signal, controller.signal)
      return Response.json({
        items: [{ slot_id: String(queries.length) }],
        next_cursor: queries.length === 1 ? 'signed+cursor' : null,
      })
    },
  )
  const slots = await listSlots(
    'clinic',
    appointment.starts_at,
    appointment.ends_at,
    'doctor',
    controller.signal,
  )
  assert.equal(slots.length, 2)
  assert.equal(queries[1].searchParams.get('cursor'), 'signed+cursor')
  for (const query of queries) {
    assert.equal(query.searchParams.get('doctor_id'), 'doctor')
    assert.equal(query.searchParams.get('from'), appointment.starts_at)
    assert.equal(query.searchParams.get('to'), appointment.ends_at)
  }
  client.clear()
})

test('appointment list binds selected clinic and cursor; detail uses its own API', async (context) => {
  const client = schedulingClient()
  const urls: string[] = []
  context.mock.method(
    globalThis,
    'fetch',
    async (url: string, init: RequestInit) => {
      urls.push(url)
      assert.equal(
        new Headers(init.headers).get('Authorization'),
        'Bearer s07-test',
      )
      return Response.json(
        url.includes('?')
          ? { items: [appointment], next_cursor: null }
          : appointment,
      )
    },
  )
  await listAppointments('clinic', 'cursor')
  const query = new URL(urls[0], 'http://localhost')
  assert.equal(query.searchParams.get('tenant_id'), 'clinic')
  assert.equal(query.searchParams.get('cursor'), 'cursor')
  assert.deepEqual(await appointmentDetail('real-appointment'), appointment)
  assert.equal(urls[1], '/api/v1/scheduling/appointments/real-appointment')
  client.clear()
})

test('failed hold is never retried or converted into a fabricated appointment', async (context) => {
  const client = schedulingClient()
  const fetch = context.mock.method(
    globalThis,
    'fetch',
    async () => new Response('private upstream trace', { status: 409 }),
  )
  await assert.rejects(
    createHold('clinic', 'slot'),
    (error) => error instanceof ApiError && error.status === 409,
  )
  assert.equal(fetch.mock.callCount(), 1)
  assert.match(schedulingError(new ApiError(409)), /changed/)
  assert.match(schedulingError(new ApiError(401)), /sign in again/)
  assert.match(schedulingError(new ApiError(403)), /membership/)
  assert.doesNotMatch(
    schedulingError(new Error('private upstream trace')),
    /private upstream trace/,
  )
  sessionStorage.clear()
  await assert.rejects(createHold('clinic', 'slot'), /Sign in/)
  assert.equal(fetch.mock.callCount(), 1)
  client.clear()
})

test('cancellation respects exact deadline and start boundaries', () => {
  const deadline = Date.parse(appointment.hold_expires_at!)
  assert.equal(canCancel(appointment, deadline - 1), true)
  assert.equal(canCancel(appointment, deadline), false)
  const confirmed = { ...appointment, status: 'confirmed' as const }
  assert.equal(canCancel(confirmed, Date.parse(confirmed.starts_at) - 1), true)
  assert.equal(canCancel(confirmed, Date.parse(confirmed.starts_at)), false)
  for (const status of [
    'cancelled',
    'expired',
    'in_progress',
    'completed',
    'no_show',
  ] as const)
    assert.equal(canCancel({ ...appointment, status }, deadline - 1), false)
})

test('checkout displays server hold, trusted snapshot and live billing handoff', () => {
  const client = schedulingClient()
  client.setQueryData(
    ['scheduling', 'appointment', 's07-test', appointment.appointment_id],
    appointment,
  )
  const markup = renderScheduling(
    client,
    createElement(LiveCheckout, {
      appointment,
      clinicName: 'Live clinic',
      doctorName: 'Live doctor',
      token: 's07-test',
      onBack: () => {},
    }),
  )
  assert.match(markup, /real-appointment/)
  assert.match(markup, /32.10/)
  assert.match(markup, /Hold expires in/)
  assert.match(markup, /Continue to payment/)
  assert.match(markup, /href="\/patient\/checkout\?appointment_id=real-appointment"/)
  assert.match(markup, /Release booking and change time/)
  assert.doesNotMatch(
    markup,
    /Demo hold|Checkout preview|No appointment has been reserved/,
  )
  client.clear()
})

test('detail renders only server metadata and hides cancellation for doctors and expired holds', () => {
  const client = schedulingClient()
  client.setQueryData(
    ['scheduling', 'appointment', 's07-test', appointment.appointment_id],
    appointment,
  )
  const props = {
    id: appointment.appointment_id,
    token: 's07-test',
    subjectId: 'patient',
    role: 'patient' as const,
    onClose: () => {},
  }
  assert.match(
    renderScheduling(client, createElement(LiveAppointmentDetails, props)),
    /Cancellation reason/,
  )
  assert.doesNotMatch(
    renderScheduling(
      client,
      createElement(LiveAppointmentDetails, { ...props, role: 'doctor' }),
    ),
    /Cancellation reason/,
  )
  client.setQueryData(
    ['scheduling', 'appointment', 's07-test', appointment.appointment_id],
    {
      ...appointment,
      status: 'expired',
      payment_resolution: 'refund_required',
    },
  )
  const markup = renderScheduling(
    client,
    createElement(LiveAppointmentDetails, props),
  )
  assert.doesNotMatch(markup, /Cancellation reason/)
  assert.match(markup, /refund review/)
  client.clear()
})
