import assert from 'node:assert/strict'
import { test } from 'node:test'
import { createElement } from 'react'
import { schedulingClient, renderScheduling } from './scheduling-helpers'
import contract from '../../../contracts/examples/prescription-order-quote.json'
import {
  createOrder,
  createQuote,
  listOrders,
  orderSnapshot,
  readyOrder,
  reconcileOrderPayment,
} from '../src/features/fulfilment/api'
import type {
  Order,
  Quote,
  OrderSnapshot,
} from '../src/features/fulfilment/api'
import {
  beginMedicationCheckout,
  canPay,
  canQuote,
  paymentMessage,
} from '../src/features/fulfilment/checkout'
import { LiveOrders } from '../src/features/fulfilment/LiveOrders'
import { parseRoute, canAccess } from '../src/navigation/access'
import { ApiError } from '../src/lib/api'

const order: Order = {
  ...contract.order_after_payment,
  status: 'awaiting_payment',
  medicine_status: 'not_ready',
  payment_status: 'unpaid',
  payment_id: null,
  medication_subtotal: { amount_minor: 2000, currency: 'SGD' },
  delivery_fee: { amount_minor: 500, currency: 'SGD' },
  total: { amount_minor: 2500, currency: 'SGD' },
  items: contract.order_after_payment.items.map((item) => ({
    ...item,
    unit_price: { amount_minor: 1000, currency: 'SGD' },
    line_total: { amount_minor: 2000, currency: 'SGD' },
  })),
}
const quote: Quote = {
  ...contract.accepted_quote,
  status: 'active',
  expires_at: new Date(Date.now() + 600000).toISOString(),
  medication_subtotal: order.medication_subtotal,
  delivery_fee: order.delivery_fee!,
  total: order.total!,
}
const payment = { ...contract.medication_payment, status: 'pending' }
const snapshot: OrderSnapshot = { order, quote, payment: null, delivery: null }
const context = { role: 'patient' as const, patientId: order.patient_id }

test('live fulfilment adapters send bearer auth and only server-owned resource references', async (t) => {
  const client = schedulingClient()
  const calls: { path: string; init: RequestInit }[] = []
  t.mock.method(
    globalThis,
    'fetch',
    async (path: string, init: RequestInit) => {
      calls.push({ path, init })
      assert.equal(
        new Headers(init.headers).get('Authorization'),
        'Bearer s07-test',
      )
      assert.equal(init.credentials, 'omit')
      assert.equal(init.cache, 'no-store')
      return Response.json(
        path.includes('quotes')
          ? quote
          : path.includes('?')
            ? { items: [], next_cursor: null }
            : order,
      )
    },
  )
  await createOrder(order.prescription_id, 'create-key')
  assert.deepEqual(JSON.parse(calls[0].init.body as string), {
    prescription_id: order.prescription_id,
  })
  await createQuote(
    order.order_id,
    {
      address_line: 'Synthetic address',
      postal_code: '038983',
      country_code: 'SG',
    },
    'quote-key',
  )
  assert.deepEqual(Object.keys(JSON.parse(calls[1].init.body as string)), [
    'destination',
  ])
  await readyOrder(order.order_id)
  assert.equal(calls[2].init.body, '{}')
  await reconcileOrderPayment(order.order_id)
  assert.equal(calls[3].init.body, '{}')
  await listOrders(order.tenant_id, 'opaque+/=')
  const url = new URL(calls[4].path, 'http://localhost')
  assert.equal(url.searchParams.get('tenant_id'), order.tenant_id)
  assert.equal(url.searchParams.get('cursor'), 'opaque+/=')
  client.clear()
})

test('order snapshots reject cross-patient, cross-tenant and mismatched payment/quote links', async (t) => {
  const client = schedulingClient()
  let mode = 'valid'
  const bound = { ...order, payment_id: payment.payment_id }
  t.mock.method(globalThis, 'fetch', async (path: string) =>
    Response.json(
      path.includes('/quotes/')
        ? { ...quote, ...(mode === 'quote' ? { order_id: 'foreign' } : {}) }
        : path.includes('/payments/')
          ? {
              ...payment,
              ...(mode === 'payment' ? { purpose: 'consultation' } : {}),
            }
          : {
              ...bound,
              ...(mode === 'patient' ? { patient_id: 'foreign' } : {}),
            },
    ),
  )
  assert.equal(
    (await orderSnapshot(order.order_id, context)).payment?.payment_id,
    payment.payment_id,
  )
  for (mode of ['quote', 'payment', 'patient'])
    await assert.rejects(orderSnapshot(order.order_id, context))
  mode = 'valid'
  await assert.rejects(
    orderSnapshot(order.order_id, { role: 'clinic_admin', tenantId: 'other' }),
  )
  client.clear()
})

test('checkout retains its key after uncertainty/reload and rotates only after verified failure', async (t) => {
  const client = schedulingClient()
  const keys: string[] = []
  let unavailable = true
  t.mock.method(
    globalThis,
    'fetch',
    async (_path: string, init: RequestInit) => {
      keys.push(new Headers(init.headers).get('Idempotency-Key')!)
      assert.deepEqual(JSON.parse(init.body as string), {
        order_id: order.order_id,
        quote_id: quote.quote_id,
      })
      if (unavailable) return new Response('', { status: 503 })
      return Response.json({
        payment,
        checkout_url: 'https://checkout.stripe.com/c/pay/test',
        expires_at: quote.expires_at,
      })
    },
  )
  await assert.rejects(beginMedicationCheckout(order.patient_id, snapshot))
  unavailable = false
  await beginMedicationCheckout(order.patient_id, snapshot)
  assert.equal(keys[0], keys[1])
  assert.equal(
    sessionStorage.getItem(`telelink.medication-return.${order.patient_id}`),
    order.order_id,
  )
  await beginMedicationCheckout(order.patient_id, {
    ...snapshot,
    order: {
      ...order,
      payment_id: payment.payment_id,
      payment_status: 'pending',
    },
    payment: { ...payment, status: 'failed' },
  })
  assert.notEqual(keys[1], keys[2])
  await beginMedicationCheckout(order.patient_id, {
    ...snapshot,
    order: {
      ...order,
      payment_id: payment.payment_id,
      payment_status: 'pending',
    },
    payment,
  })
  assert.equal(keys[2], keys[3])
  client.clear()
})

test('a reservation without a payment row cannot mint a fresh browser attempt', async () => {
  const client = schedulingClient()
  const pending = {
    ...snapshot,
    order: {
      ...order,
      payment_id: payment.payment_id,
      payment_status: 'pending' as const,
    },
  }
  await assert.rejects(
    beginMedicationCheckout(order.patient_id, pending),
    /existing payment needs reconciliation/,
  )
  client.clear()
})

test('expiry equality and terminal states block pay; pending blocks re-quote; received payment waits for fulfilment', () => {
  assert.equal(canPay(snapshot, Date.parse(quote.expires_at) - 1), true)
  assert.equal(canPay(snapshot, Date.parse(quote.expires_at)), false)
  assert.equal(canQuote(snapshot), true)
  const pending = {
    ...snapshot,
    order: {
      ...order,
      payment_id: payment.payment_id,
      payment_status: 'pending' as const,
    },
    payment,
  }
  assert.equal(canQuote(pending), false)
  const received = { ...pending, payment: { ...payment, status: 'succeeded' } }
  assert.equal(canPay(received), false)
  assert.match(paymentMessage(received), /waiting for the order to confirm/)
  assert.equal(
    canPay({ ...snapshot, order: { ...order, status: 'cancelled' } }),
    false,
  )
  assert.equal(
    canPay({
      ...snapshot,
      order: { ...order, payment_status: 'refund_required' },
    }),
    false,
  )
  assert.match(
    paymentMessage({
      ...received,
      payment: {
        ...payment,
        status: 'succeeded',
        resolution: 'refund_required',
      },
    }),
    /No automatic refund/,
  )
})

test('real order pages have protected exact routes, load server data and never substitute fixtures on errors', async (t) => {
  const route = parseRoute('/patient/medication-orders')
  assert.deepEqual(route, { kind: 'medication-orders', role: 'patient' })
  assert.equal(
    canAccess({ subject_id: 'p', global_roles: [], memberships: [] }, route),
    false,
  )
  assert.deepEqual(parseRoute('/patient/medication-orders/paid'), {
    kind: 'missing',
  })
  const client = schedulingClient({
    subject_id: order.patient_id,
    global_roles: ['patient'],
    memberships: [],
  })
  const oldWindow = Object.getOwnPropertyDescriptor(globalThis, 'window')
  Object.defineProperty(globalThis, 'window', {
    value: { location: { search: '' } },
    configurable: true,
  })
  t.mock.method(globalThis, 'fetch', async () => {
    throw new ApiError(503)
  })
  try {
    const markup = renderScheduling(
      client,
      createElement(LiveOrders, { role: 'patient' }),
    )
    assert.match(markup, /Loading medication orders/)
    assert.doesNotMatch(
      markup,
      /Demo order|synthetic data|Simulate|Tracking example/,
    )
  } finally {
    if (oldWindow) Object.defineProperty(globalThis, 'window', oldWindow)
    else Reflect.deleteProperty(globalThis, 'window')
    client.clear()
  }
})
