import assert from 'node:assert/strict'
import { test } from 'node:test'
import { schedulingClient } from './scheduling-helpers'
import { paymentFixtures } from '../src/features/payments/fixtures'
import {
  listPayments,
  paymentDetail,
  paymentTotals,
  stripeCheckoutUrl,
} from '../src/features/payments/api'
import {
  beginCheckout,
  canCheckout,
  liveCheckoutState,
} from '../src/features/checkout/live'
import type { Appointment } from '../src/features/scheduling/api'
import { parseRoute, canAccess } from '../src/navigation/access'
import { createElement } from 'react'
import { renderScheduling } from './scheduling-helpers'
import { LiveCheckoutPage } from '../src/features/checkout/LiveCheckoutPage'
import { ApiError } from '../src/lib/api'

const payment = { ...paymentFixtures[0], status: 'pending', resolution: 'none' }
const appointment: Appointment = {
  appointment_id: payment.appointment_id!,
  tenant_id: payment.tenant_id,
  patient_id: payment.patient_id,
  doctor_id: 'doctor',
  slot_id: 'slot',
  starts_at: new Date(Date.now() + 3600000).toISOString(),
  ends_at: new Date(Date.now() + 5400000).toISOString(),
  hold_expires_at: new Date(Date.now() + 600000).toISOString(),
  consultation_price: { amount_minor: 5000, currency: 'SGD' },
  status: 'pending_payment',
  payment_id: payment.payment_id,
  payment_resolution: 'awaiting_payment',
  created_at: '',
  updated_at: '',
}
const checkout = {
  payment,
  checkout_url: 'https://checkout.stripe.com/c/pay/test',
  expires_at: appointment.hold_expires_at!,
}

test('billing reads send bearer auth, scoped filters and opaque cursor without credentials/cache', async (context) => {
  const client = schedulingClient()
  const paths: string[] = []
  context.mock.method(
    globalThis,
    'fetch',
    async (url: string, init: RequestInit) => {
      paths.push(url)
      assert.equal(
        new Headers(init.headers).get('Authorization'),
        'Bearer s07-test',
      )
      assert.equal(init.credentials, 'omit')
      assert.equal(init.cache, 'no-store')
      return Response.json(
        url.includes('commission-totals')
          ? { payment_count: 3 }
          : url.includes('?')
            ? { items: [payment], next_cursor: 'opaque' }
            : payment,
      )
    },
  )
  assert.equal(
    (await paymentDetail(payment.payment_id)).payment_id,
    payment.payment_id,
  )
  assert.equal(
    (
      await listPayments(
        payment.tenant_id,
        'consultation',
        'succeeded',
        'a+/=&',
      )
    ).next_cursor,
    'opaque',
  )
  assert.equal(
    (await paymentTotals(payment.tenant_id, 'consultation')).payment_count,
    3,
  )
  const list = new URL(paths[1], 'http://localhost')
  assert.equal(list.searchParams.get('tenant_id'), payment.tenant_id)
  assert.equal(list.searchParams.get('cursor'), 'a+/=&')
  assert.equal(list.searchParams.get('status'), 'succeeded')
  assert.equal(
    new URL(paths[2], 'http://localhost').searchParams.has('status'),
    false,
  )
  client.clear()
})

test('uncertain checkout retries retain key across reloads; authoritative failure permits a new key', async (context) => {
  const client = schedulingClient()
  const keys: string[] = []
  context.mock.method(
    globalThis,
    'fetch',
    async (_url: string, init: RequestInit) => {
      assert.deepEqual(JSON.parse(String(init.body)), {
        appointment_id: appointment.appointment_id,
      })
      keys.push(new Headers(init.headers).get('Idempotency-Key')!)
      if (keys.length === 1) throw new Error('lost response')
      return Response.json(checkout)
    },
  )
  await assert.rejects(
    beginCheckout(appointment.patient_id, appointment, payment),
    /lost response/,
  )
  await beginCheckout(appointment.patient_id, appointment, payment)
  assert.equal(keys[0], keys[1])
  await beginCheckout(appointment.patient_id, appointment, {
    ...payment,
    status: 'failed',
  })
  assert.notEqual(keys[1], keys[2])
  await beginCheckout(appointment.patient_id, appointment, payment)
  assert.equal(keys[2], keys[3])
  assert.equal(
    sessionStorage.getItem(
      `telelink.checkout-return.${appointment.patient_id}`,
    ),
    appointment.appointment_id,
  )
  await assert.rejects(
    beginCheckout('foreign-patient', appointment, payment),
    /not payable/,
  )
  client.clear()
})

test('live status checks linkage and authoritative booking confirmation; paid and expired bookings cannot pay', () => {
  assert.equal(liveCheckoutState(appointment, payment), 'pending')
  const paid = { ...payment, status: 'succeeded' }
  assert.equal(
    liveCheckoutState(
      { ...appointment, status: 'no_show', payment_resolution: 'confirmed' },
      paid,
    ),
    'no_show',
  )
  assert.equal(
    liveCheckoutState(
      { ...appointment, status: 'completed', payment_resolution: 'confirmed' },
      paid,
    ),
    'success',
  )
  assert.equal(liveCheckoutState(appointment, paid), 'confirming')
  assert.equal(
    liveCheckoutState(
      { ...appointment, status: 'confirmed', payment_resolution: 'confirmed' },
      paid,
    ),
    'success',
  )
  assert.equal(
    liveCheckoutState(
      {
        ...appointment,
        status: 'expired',
        payment_resolution: 'refund_required',
      },
      paid,
    ),
    'refund_required',
  )
  assert.equal(
    liveCheckoutState(appointment, { ...payment, status: 'refunded' }),
    'refunded',
  )
  assert.throws(
    () => liveCheckoutState(appointment, { ...payment, tenant_id: 'foreign' }),
    /does not match/,
  )
  assert.throws(
    () =>
      liveCheckoutState(appointment, { ...payment, payment_id: 'old-attempt' }),
    /does not match/,
  )
  assert.equal(canCheckout(appointment, paid), false)
  assert.equal(
    canCheckout({ ...appointment, status: 'cancelled' }, payment),
    false,
  )
  assert.equal(
    canCheckout(appointment, payment, Date.parse(appointment.hold_expires_at!)),
    false,
  )
  assert.equal(
    canCheckout(appointment, { ...payment, status: 'refund_failed' }),
    false,
  )
})

test('checkout redirects reject foreign hosts, credentials, invalid and expired deadlines', () => {
  assert.equal(stripeCheckoutUrl(checkout), checkout.checkout_url)
  for (const checkout_url of [
    'https://checkout.stripe.com.evil.test/a',
    'javascript:alert(1)',
    'http://checkout.stripe.com/a',
    'https://user@checkout.stripe.com/a',
  ])
    assert.throws(() => stripeCheckoutUrl({ ...checkout, checkout_url }))
  assert.throws(() => stripeCheckoutUrl({ ...checkout, expires_at: 'invalid' }))
  assert.throws(() =>
    stripeCheckoutUrl(checkout, Date.parse(checkout.expires_at)),
  )
})

test('live return and recovery routes require patient access', () => {
  for (const path of [
    '/patient/checkout',
    '/payments/return',
    '/appointments',
  ]) {
    const route = parseRoute(path)
    assert.deepEqual(route, { kind: 'checkout', role: 'patient' })
    assert.equal(
      canAccess(
        { subject_id: 'doctor', global_roles: [], memberships: [] },
        route,
      ),
      false,
    )
  }
})

test('live return ignores success flags and shows server booking references and amount', (context) => {
  const client = schedulingClient({
    subject_id: appointment.patient_id,
    global_roles: ['patient'],
    memberships: [],
  })
  const priorWindow = Object.getOwnPropertyDescriptor(globalThis, 'window')
  Object.defineProperty(globalThis, 'window', {
    configurable: true,
    value: {
      location: {
        search: `?appointment_id=${appointment.appointment_id}&success=true&status=succeeded`,
      },
    },
  })
  context.after(() => {
    client.clear()
    if (priorWindow) Object.defineProperty(globalThis, 'window', priorWindow)
    else Reflect.deleteProperty(globalThis, 'window')
  })
  const key = [
    'billing',
    'return',
    's07-test',
    appointment.patient_id,
    appointment.appointment_id,
  ]
  client.setQueryData(key, {
    appointment,
    payment,
    state: liveCheckoutState(appointment, payment),
  })
  const pending = renderScheduling(client, createElement(LiveCheckoutPage))
  assert.match(pending, /Payment pending/)
  assert.match(pending, new RegExp(appointment.appointment_id))
  assert.match(pending, /Original booking deadline/)
  assert.doesNotMatch(pending, /<h1[^>]*>Appointment confirmed/)
  const held = { ...appointment, status: 'held' as const, payment_id: null }
  client.setQueryData(key, {
    appointment: held,
    payment: null,
    state: liveCheckoutState(held, null),
  })
  const ready = renderScheduling(client, createElement(LiveCheckoutPage))
  assert.match(ready, /Ready for payment/)
  assert.match(ready, /\$50.00/)
  assert.match(ready, /Continue to secure checkout/)
  assert.doesNotMatch(ready, /Payment reference<\/dt>/)
})

test('billing failures propagate without retries or fixture fallbacks', async (context) => {
  const client = schedulingClient()
  let status = 401
  let calls = 0
  context.mock.method(globalThis, 'fetch', async () => {
    calls++
    return Response.json({ error: { message: 'Unavailable' } }, { status })
  })
  for (status of [401, 403, 404, 503]) {
    await assert.rejects(
      paymentDetail(payment.payment_id),
      (error) => error instanceof ApiError && error.status === status,
    )
  }
  assert.equal(calls, 4)
  client.clear()
})
