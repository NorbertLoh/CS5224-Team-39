import assert from 'node:assert/strict'
import { test } from 'node:test'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { canAccess, parseRoute } from '../src/navigation/access'
import {
  paymentFixtures,
  fixtureClinics,
} from '../src/features/payments/fixtures'
import {
  clinicPayments,
  commissionTotals,
} from '../src/features/payments/model'
import { schedulingClient, renderScheduling } from './scheduling-helpers'
import { ClinicPayments } from '../src/features/payments/ClinicPayments'
import { PaymentHistory } from '../src/features/payments/PaymentHistory'

const clinicA = fixtureClinics[0].tenant_id
const clinicB = fixtureClinics[1].tenant_id

test('payments route follows active clinic admin membership and platform policy', () => {
  const route = parseRoute(`/clinic-admin/clinics/${clinicA}/payments`)
  assert.deepEqual(route, {
    kind: 'payments',
    role: 'clinic_admin',
    tenantId: clinicA,
  })
  const admin = {
    subject_id: 'admin',
    global_roles: [],
    memberships: [
      { tenant_id: clinicA, roles: ['clinic_admin'], status: 'active' },
    ],
  }
  assert.equal(canAccess(admin, route), true)
  assert.equal(
    canAccess(admin, parseRoute(`/clinic-admin/clinics/${clinicB}/payments`)),
    false,
  )
  assert.equal(
    canAccess(
      {
        ...admin,
        memberships: [{ ...admin.memberships[0], status: 'revoked' }],
      },
      route,
    ),
    false,
  )
  for (const global_roles of [['patient'], []])
    assert.equal(
      canAccess({ subject_id: 'other', global_roles, memberships: [] }, route),
      false,
    )
  assert.equal(
    canAccess(
      {
        subject_id: 'platform',
        global_roles: ['platform_admin'],
        memberships: [],
      },
      route,
    ),
    true,
  )
  assert.deepEqual(parseRoute('/clinic-admin/clinics/bad-id/payments'), {
    kind: 'missing',
  })
})

test('clinic totals exclude unresolved and refund states and use stored delivery commission', () => {
  assert.deepEqual(commissionTotals(paymentFixtures, clinicA), {
    count: 5,
    amount: 11500,
    commission: 1050,
    clinic: 10450,
  })
  assert.deepEqual(commissionTotals(paymentFixtures, clinicB), {
    count: 2,
    amount: 6000,
    commission: 600,
    clinic: 5400,
  })
  assert.deepEqual(
    commissionTotals(paymentFixtures, clinicA, 'medication_delivery'),
    { count: 2, amount: 4000, commission: 300, clinic: 3700 },
  )
  // Changing a rate today must not rewrite any historic commission snapshot.
  const changedRates = paymentFixtures.map((payment) => ({
    ...payment,
    commission_bps: 9900,
  }))
  assert.deepEqual(
    commissionTotals(changedRates, clinicA),
    commissionTotals(paymentFixtures, clinicA),
  )
  const onlyExcluded = paymentFixtures.filter(
    (payment) =>
      payment.status !== 'succeeded' || payment.resolution !== 'none',
  )
  assert.deepEqual(commissionTotals(onlyExcluded, clinicA), {
    count: 0,
    amount: 0,
    commission: 0,
    clinic: 0,
  })
})

test('history filters preserve tenant isolation, purpose and deterministic order without mutating fixtures', () => {
  const before = JSON.stringify(paymentFixtures)
  const medication = clinicPayments(
    paymentFixtures,
    clinicA,
    'medication_delivery',
    'succeeded',
  )
  assert.equal(medication.length, 2)
  assert.ok(
    medication.every(
      (payment) =>
        payment.tenant_id === clinicA &&
        payment.purpose === 'medication_delivery',
    ),
  )
  const refunds = clinicPayments(
    paymentFixtures,
    clinicA,
    'all',
    'refund_required',
  )
  assert.equal(refunds.length, 3)
  assert.ok(
    refunds.every((payment) => payment.resolution === 'refund_required'),
  )
  assert.deepEqual(clinicPayments(paymentFixtures, 'unknown-clinic'), [])
  const reversed = [...paymentFixtures].reverse()
  assert.deepEqual(
    clinicPayments(reversed, clinicA),
    clinicPayments(paymentFixtures, clinicA),
  )
  assert.equal(JSON.stringify(paymentFixtures), before)
})

test('totals reject unsafe and non-SGD amounts rather than misreport money', () => {
  const payment = paymentFixtures[0]
  assert.throws(
    () =>
      commissionTotals(
        [{ ...payment, amount: { amount_minor: 1.5, currency: 'SGD' } }],
        clinicA,
      ),
    /invalid amounts/,
  )
  assert.throws(
    () =>
      commissionTotals(
        [{ ...payment, amount: { amount_minor: 100, currency: 'USD' } }],
        clinicA,
      ),
    /invalid amounts/,
  )
  const huge = {
    ...payment,
    amount: { amount_minor: Number.MAX_SAFE_INTEGER, currency: 'SGD' },
  }
  assert.throws(
    () => commissionTotals([huge, payment], clinicA),
    /supported range/,
  )
})

test('live clinic screen uses scoped server history and server totals', () => {
  const client = schedulingClient()
  const rows = clinicPayments(paymentFixtures, clinicA)
  client.setQueryData(
    ['billing', 'history', 's07-test', clinicA, 'all', 'all'],
    {
      pages: [{ items: rows, next_cursor: 'next-page' }],
      pageParams: [null],
    },
  )
  client.setQueryData(['billing', 'totals', 's07-test', clinicA, 'all'], {
    payment_count: 1,
    amount: { amount_minor: 9876, currency: 'SGD' },
    commission_amount: { amount_minor: 123, currency: 'SGD' },
    clinic_amount: { amount_minor: 9753, currency: 'SGD' },
  })
  const markup = renderScheduling(
    client,
    createElement(ClinicPayments, { tenantId: clinicA }),
  )
  assert.match(markup, /aria-label="Clinic management"/)
  assert.match(markup, /\$98.76/)
  assert.match(markup, /\$1.23/)
  assert.match(markup, /not a net payout/)
  assert.match(markup, /Manual refund review required/)
  assert.match(markup, /Load more payments/)
  assert.doesNotMatch(markup, /Fixture preview|fixture payments/)
  for (const foreign of clinicPayments(paymentFixtures, clinicB))
    assert.ok(!markup.includes(foreign.payment_id))
  client.clear()
})

test('live clinic screen does not substitute fixture totals while loading', () => {
  const client = schedulingClient()
  const markup = renderScheduling(
    client,
    createElement(ClinicPayments, { tenantId: 'unknown-clinic' }),
  )
  assert.match(markup, /Loading payments/)
  assert.match(markup, /Loading commission totals/)
  assert.doesNotMatch(markup, /Demo Clinic|Payment details|\$0.00/)
  assert.match(
    renderToStaticMarkup(createElement(PaymentHistory, { payments: [] })),
    /role="status"/,
  )
  client.clear()
})
