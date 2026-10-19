import assert from 'node:assert/strict'
import { test } from 'node:test'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { canAccess, parseRoute } from '../src/navigation/access'
import {
  addressError,
  canCheckout,
  fixtureNow,
  initialState,
  order,
  orderReducer,
  prescription,
} from '../src/features/medication-orders/model'
import type { OrderState } from '../src/features/medication-orders/model'
import { MedicationOrderPreview } from '../src/features/medication-orders/MedicationOrderPreview'
import { OrderSummary } from '../src/features/medication-orders/OrderSummary'
import { MedicationPayment } from '../src/features/medication-orders/MedicationPayment'
import { DeliveryQuote } from '../src/features/medication-orders/DeliveryQuote'

function quoted() {
  return orderReducer(orderReducer(initialState(), { type: 'create' }), {
    type: 'quote',
  })
}

test('medication preview is an exact patient-only route', () => {
  const route = parseRoute('/patient/medication-order-preview')
  assert.deepEqual(route, {
    kind: 'medication-order-preview',
    role: 'patient',
  })
  assert.equal(
    canAccess(
      { subject_id: 'p', global_roles: ['patient'], memberships: [] },
      route,
    ),
    true,
  )
  for (const role of ['doctor', 'clinic_admin', 'platform_admin'])
    assert.equal(
      canAccess(
        { subject_id: 'x', global_roles: [role], memberships: [] },
        route,
      ),
      false,
    )
  assert.deepEqual(parseRoute('/patient/medication-order-preview/paid'), {
    kind: 'missing',
  })
})

test('fixed quantities and SGD prices match the linked C04 contract example', () => {
  assert.equal(order.prescription_id, prescription.prescription_id)
  for (const item of order.items) {
    assert.equal(
      item.quantity,
      prescription.items.find(
        (rx) => rx.prescription_item_id === item.prescription_item_id,
      )?.quantity,
    )
    assert.equal(item.unit_price.currency, 'SGD')
    assert.equal(
      item.line_total.amount_minor,
      item.quantity * item.unit_price.amount_minor,
    )
  }
  const state = quoted()
  assert.equal(
    state.quote?.medicationSubtotal,
    order.items.reduce((sum, item) => sum + item.line_total.amount_minor, 0),
  )
  assert.equal(
    state.quote?.total,
    state.quote!.medicationSubtotal + state.quote!.deliveryFee,
  )
  const markup = renderToStaticMarkup(createElement(OrderSummary, { state }))
  assert.match(markup, /\$20.00/)
  assert.match(markup, /\$5.00/)
  assert.match(markup, /\$25.00/)
  assert.doesNotMatch(markup, /<input/)
})

test('quote requires an order and validated structured Singapore address', () => {
  assert.equal(orderReducer(initialState(), { type: 'quote' }).quote, null)
  for (const address of [
    { address_line: ' ', postal_code: '018956', country_code: 'SG' as const },
    { address_line: 'Demo', postal_code: '18956', country_code: 'SG' as const },
    {
      address_line: 'Demo',
      postal_code: '01895x',
      country_code: 'SG' as const,
    },
  ]) {
    assert.ok(addressError(address))
    const result = orderReducer(
      { ...initialState(), created: true, address },
      { type: 'quote' },
    )
    assert.equal(result.quote, null)
    assert.ok(result.error)
  }
})

test('address changes remove the old quote; refresh creates a separate immutable snapshot', () => {
  const state = quoted()
  const original = structuredClone(state.quote)
  const changed = orderReducer(state, {
    type: 'address',
    field: 'address_line',
    value: '20 Demo Street',
  })
  assert.equal(changed.quote, null)
  assert.equal(canCheckout(changed), false)
  const refreshed = orderReducer(changed, { type: 'quote' })
  assert.notEqual(refreshed.quote?.quote_id, state.quote?.quote_id)
  assert.equal(refreshed.quote?.destination.address_line, '20 Demo Street')
  assert.deepEqual(state.quote, original)
})

test('quote deadline equality blocks checkout, but a fresh quote allows it', () => {
  const state = quoted()
  const deadline = state.quote!.expiresAt
  assert.equal(deadline, fixtureNow + 600_000)
  assert.equal(canCheckout({ ...state, now: deadline - 1 }), true)
  const expired = orderReducer(state, {
    type: 'tick',
    elapsed: deadline - state.now,
  })
  assert.equal(canCheckout(expired), false)
  assert.equal(orderReducer(expired, { type: 'checkout' }).payment, 'none')
  assert.equal(canCheckout(orderReducer(expired, { type: 'quote' })), true)
  assert.equal(
    orderReducer(expired, { type: 'tick', elapsed: 1000 }).now,
    deadline + 1000,
  )
})

test('pending, cancelled return and unknown status preserve the accepted attempt beyond expiry', () => {
  const pending = orderReducer(quoted(), { type: 'checkout' })
  for (const outcome of ['pending', 'cancelled', 'unknown'] as const) {
    const state = orderReducer(orderReducer(pending, { type: 'expire' }), {
      type: 'check',
      outcome,
    })
    assert.equal(canCheckout(state), false)
    assert.deepEqual(orderReducer(state, { type: 'quote' }), state)
    assert.deepEqual(orderReducer(state, { type: 'checkout' }), state)
    assert.deepEqual(
      orderReducer(state, {
        type: 'address',
        field: 'postal_code',
        value: '123456',
      }),
      state,
    )
    const markup = paymentScreen(state)
    assert.doesNotMatch(markup, /Retry demo payment/)
    assert.match(markup, /Check demo payment status/)
    if (outcome === 'cancelled')
      assert.match(markup, /does not mean payment failed/)
  }
})

test('only verified failure can retry while quote is active; success never regresses', () => {
  const pending = orderReducer(quoted(), { type: 'checkout' })
  const failed = orderReducer(pending, { type: 'check', outcome: 'failed' })
  assert.equal(canCheckout(failed), true)
  assert.equal(canCheckout(orderReducer(failed, { type: 'expire' })), false)
  const confirming = orderReducer(pending, {
    type: 'check',
    outcome: 'confirming',
  })
  assert.equal(canCheckout(confirming), false)
  assert.deepEqual(
    orderReducer(confirming, { type: 'check', outcome: 'failed' }),
    confirming,
  )
  const paid = orderReducer(confirming, { type: 'check', outcome: 'paid' })
  assert.equal(canCheckout(paid), false)
  assert.match(paymentScreen(paid), /does not confirm dispatch or delivery/)
  assert.deepEqual(
    orderReducer(paid, { type: 'check', outcome: 'pending' }),
    paid,
  )
  const refund = orderReducer(pending, {
    type: 'check',
    outcome: 'refund_required',
  })
  assert.equal(canCheckout(refund), false)
  assert.match(paymentScreen(refund), /no automatic refund is promised/)
})

test('unavailable quote can be retried; missing and expired quotes never offer checkout', () => {
  const failed = orderReducer(
    { ...initialState(), created: true },
    { type: 'quote', unavailable: true },
  )
  assert.equal(failed.quote, null)
  assert.match(failed.error!, /unavailable/)
  assert.equal(canCheckout(failed), false)
  assert.equal(canCheckout(orderReducer(failed, { type: 'quote' })), true)
  const expired = orderReducer(quoted(), { type: 'expire' })
  const markup = renderToStaticMarkup(
    createElement(DeliveryQuote, {
      state: expired,
      dispatch() {},
      unavailable: false,
    }),
  )
  assert.match(markup, /Quote expired/)
  assert.match(markup, /disabled=""[^>]*>Preview payment/)
})

test('initial preview explicitly discloses synthetic data and does not read success from URL parameters', () => {
  const markup = renderToStaticMarkup(createElement(MedicationOrderPreview))
  assert.match(markup, /No payment is taken/)
  assert.match(markup, /Create demo medication order/)
  assert.doesNotMatch(markup, /Medication payment confirmed/)
})

function paymentScreen(state: OrderState) {
  return renderToStaticMarkup(
    createElement(MedicationPayment, {
      state,
      outcome: 'pending',
      dispatch() {},
    }),
  )
}
