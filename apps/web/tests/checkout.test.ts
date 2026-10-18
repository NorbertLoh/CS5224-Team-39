import assert from 'node:assert/strict'
import { test } from 'node:test'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { checkoutState } from '../src/features/checkout/status'
import { checkoutSummary, fixtureNow, scenarios } from '../src/features/checkout/fixtures'
import { CheckoutStatus } from '../src/features/checkout/CheckoutStatus'
import { CheckoutPreview } from '../src/features/checkout/CheckoutPreview'
import { canAccess, parseRoute } from '../src/navigation/access'

test('checkout preview requires the patient role and an exact route', () => {
  const route = parseRoute('/patient/checkout-preview')
  assert.deepEqual(route, { kind: 'checkout-preview', role: 'patient' })
  assert.equal(
    canAccess(
      { subject_id: 'p', global_roles: ['patient'], memberships: [] },
      route,
    ),
    true,
  )
  assert.equal(
    canAccess({ subject_id: 'd', global_roles: [], memberships: [] }, route),
    false,
  )
  assert.deepEqual(parseRoute('/patient/checkout-preview/success'), {
    kind: 'missing',
  })
})

test('redirect parameters cannot turn the default return into a success screen', () => {
  // The feature has no URL input: success/session_id/cancel flags cannot set truth.
  const markup = renderToStaticMarkup(createElement(CheckoutPreview))
  assert.match(markup, /Welcome back from checkout/)
  assert.match(markup, /Your return does not confirm payment/)
  assert.match(markup, /No payment is taken/)
  assert.doesNotMatch(markup, /<h1[^>]*>Appointment confirmed/)
})

test('a successful payment waits for scheduling; recovered bookings require confirmation', () => {
  assert.equal(
    checkoutState(scenarios.confirming.snapshot, fixtureNow),
    'confirming',
  )
  assert.equal(checkoutState(scenarios.success.snapshot, fixtureNow), 'success')
  assert.equal(
    checkoutState(scenarios.recovered.snapshot, fixtureNow),
    'success',
  )
  assert.equal(
    checkoutState(
      { ...scenarios.confirming.snapshot, appointment: 'expired' },
      fixtureNow,
    ),
    'confirming',
  )
  assert.equal(
    checkoutState(scenarios.refund.snapshot, fixtureNow),
    'refund_required',
  )
  assert.equal(
    checkoutState(scenarios.refundPending.snapshot, fixtureNow),
    'refund_pending',
  )
  assert.equal(
    checkoutState(scenarios.refunded.snapshot, fixtureNow),
    'refunded',
  )
})

test('failed payment is retryable only before the exact original deadline', () => {
  const snapshot = scenarios.failed.snapshot
  const deadline = Date.parse(snapshot.holdExpiresAt!)
  assert.equal(checkoutState(snapshot, deadline - 1), 'failed')
  assert.equal(checkoutState(snapshot, deadline), 'expired')
  assert.equal(
    checkoutState({ ...snapshot, holdExpiresAt: null }, fixtureNow),
    'expired',
  )
  assert.equal(
    checkoutState({ ...snapshot, holdExpiresAt: 'invalid' }, fixtureNow),
    'expired',
  )
  assert.equal(
    checkoutState({ ...snapshot, appointment: 'cancelled' }, fixtureNow),
    'cancelled',
  )
  assert.equal(
    checkoutState(scenarios.cancelled.snapshot, fixtureNow),
    'pending',
  )
})

function screen(state: Parameters<typeof CheckoutStatus>[0]['state']) {
  return renderToStaticMarkup(
    createElement(CheckoutStatus, {
      state,
      summary: state === 'missing' ? undefined : checkoutSummary,
      onCheck() {},
      onRetry() {},
      cancelledReturn: true,
    }),
  )
}

test('unknown, pending and paid outcomes never offer a payment retry', () => {
  for (const state of [
    'return',
    'pending',
    'confirming',
    'error',
    'missing',
    'expired',
    'success',
    'refund_required',
    'refund_pending',
    'refunded',
  ] as const) {
    const markup = screen(state)
    assert.doesNotMatch(markup, /Retry payment/)
    assert.match(markup, /href="\/patient"/)
  }
  assert.match(screen('failed'), /Retry payment/)
  assert.match(screen('pending'), /Do not start another payment/)
  assert.match(screen('error'), /outcome is unknown/)
  assert.match(screen('return'), /does not mean the payment failed/)
  assert.doesNotMatch(screen('missing'), /Payment reference<\/dt>/)
})

test('refund exception shows manual support, references and no confirmation promise', () => {
  const markup = screen('refund_required')
  assert.match(markup, /manual refund/)
  assert.match(markup, /No automatic refund is promised/)
  assert.match(markup, /Appointment reference/)
  assert.match(markup, /Payment reference/)
  assert.match(markup, /\$25.00/)
  assert.match(markup, /SGT/)
  assert.doesNotMatch(markup, /<h1[^>]*>Appointment confirmed/)
})
