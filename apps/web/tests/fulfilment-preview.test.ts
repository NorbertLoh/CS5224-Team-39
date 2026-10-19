import assert from 'node:assert/strict'
import { test } from 'node:test'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { canAccess, parseRoute } from '../src/navigation/access'
import type { Identity } from '../src/features/clinics/api'
import {
  demoPatientId,
  demoTenantId,
  examples,
  fixtureOrders,
} from '../src/features/fulfilment/fixtures'
import {
  canMarkReady,
  markReady,
  trackingGuidance,
  visibleOrders,
} from '../src/features/fulfilment/model'
import type { PreviewContext } from '../src/features/fulfilment/model'
import { TrackingOrderDetails } from '../src/features/fulfilment/TrackingOrderDetails'
import { TrackingOrderList } from '../src/features/fulfilment/TrackingOrderList'
import { FulfilmentPreview } from '../src/features/fulfilment/FulfilmentPreview'
import contract from '../../../contracts/examples/prescription-order-quote.json'

const clinic: PreviewContext = { role: 'clinic_admin', tenantId: demoTenantId }
const patient: PreviewContext = { role: 'patient', patientId: demoPatientId }
const otherClinic = '11111111-1111-4111-8111-111111111111'
const identity: Identity = {
  subject_id: 'demo-admin',
  global_roles: [],
  memberships: [
    { tenant_id: demoTenantId, roles: ['clinic_admin'], status: 'active' },
  ],
}

test('tracking routes enforce patient or active owning-clinic administration', () => {
  const patientRoute = parseRoute('/patient/delivery-tracking-preview')
  assert.deepEqual(patientRoute, {
    kind: 'delivery-tracking-preview',
    role: 'patient',
  })
  assert.equal(
    canAccess({ ...identity, global_roles: ['patient'] }, patientRoute),
    true,
  )
  assert.equal(canAccess(identity, patientRoute), false)
  const clinicRoute = parseRoute(
    `/clinic-admin/clinics/${demoTenantId}/fulfilment-preview`,
  )
  assert.deepEqual(clinicRoute, {
    kind: 'fulfilment-preview',
    role: 'clinic_admin',
    tenantId: demoTenantId,
  })
  assert.equal(canAccess(identity, clinicRoute), true)
  assert.equal(
    canAccess(
      identity,
      parseRoute(`/clinic-admin/clinics/${otherClinic}/fulfilment-preview`),
    ),
    false,
  )
  for (const roles of [[], ['doctor']])
    assert.equal(
      canAccess(
        {
          ...identity,
          memberships: [{ tenant_id: demoTenantId, roles, status: 'active' }],
        },
        clinicRoute,
      ),
      false,
    )
  assert.equal(
    canAccess(
      {
        ...identity,
        memberships: [{ ...identity.memberships[0], status: 'revoked' }],
      },
      clinicRoute,
    ),
    false,
  )
  assert.equal(
    canAccess(
      { ...identity, global_roles: ['platform_admin'], memberships: [] },
      clinicRoute,
    ),
    false,
  )
  for (const path of [
    '/patient/delivery-tracking-preview/delivered',
    '/clinic-admin/clinics/wrong/fulfilment-preview',
  ])
    assert.deepEqual(parseRoute(path), { kind: 'missing' })
})

test('fixture lists and readiness actions stay within patient and clinic context', () => {
  const orders = fixtureOrders('active')
  const mixed = [
    ...orders,
    {
      ...orders[0],
      order_id: 'foreign',
      tenant_id: otherClinic,
      patient_id: 'another-patient',
    },
  ]
  assert.deepEqual(visibleOrders(mixed, clinic), orders)
  assert.deepEqual(visibleOrders(mixed, patient), orders)
  assert.equal(canMarkReady(orders[0], patient), false)
  assert.equal(
    canMarkReady(orders[0], { role: 'clinic_admin', tenantId: otherClinic }),
    false,
  )
  assert.equal(markReady(orders[0], patient), orders[0])
})

test('readiness is retry-safe and changes neither payment, quote nor delivery', () => {
  for (const order of fixtureOrders('active').slice(0, 2)) {
    const before = structuredClone(order)
    assert.equal(canMarkReady(order, clinic), true)
    const ready = markReady(order, clinic)
    assert.equal(ready.medicine_status, 'ready')
    assert.deepEqual(
      {
        ...ready,
        medicine_status: order.medicine_status,
        updated_at: order.updated_at,
      },
      before,
    )
    assert.deepEqual(order, before)
    assert.equal(markReady(ready, clinic), ready)
    if (order.payment_status === 'unpaid')
      assert.match(trackingGuidance(ready), /waiting for confirmed payment/)
    else assert.match(trackingGuidance(ready), /no courier is confirmed yet/)
  }
})

test('readiness rejects unissued, inactive and refund orders', () => {
  const order = fixtureOrders('active')[0]
  for (const status of ['draft', 'voided'] as const)
    assert.equal(
      canMarkReady({ ...order, prescription_status: status }, clinic),
      false,
    )
  for (const example of [
    'submitting',
    'submitted',
    'delivered',
    'cancelled',
    'failed',
    'unknown',
    'refund',
    'refunded',
  ] as const) {
    const snapshot = fixtureOrders(example)[0]
    assert.equal(canMarkReady(snapshot, clinic), false)
    assert.equal(markReady(snapshot, clinic), snapshot)
  }
})

test('only explicit verified delivery states claim courier acceptance, pickup or completion', () => {
  const both = fixtureOrders('active')[2]
  assert.equal(both.payment_status, 'succeeded')
  assert.equal(both.medicine_status, 'ready')
  assert.equal(both.delivery, null)
  assert.match(trackingGuidance(both), /Waiting for delivery submission/)
  assert.match(
    trackingGuidance(fixtureOrders('submitted')[0]),
    /Pickup and completion are not yet confirmed/,
  )
  assert.match(
    trackingGuidance(fixtureOrders('picked_up')[0]),
    /Delivery is not yet confirmed/,
  )
  assert.match(
    trackingGuidance(fixtureOrders('delivered')[0]),
    /completion is confirmed/,
  )
  assert.match(
    trackingGuidance(fixtureOrders('unknown')[0]),
    /reconcile the existing attempt/,
  )
  assert.match(
    trackingGuidance(fixtureOrders('failed')[0]),
    /no automatic resubmission/,
  )
  assert.match(
    trackingGuidance(fixtureOrders('cancelled')[0]),
    /does not itself confirm a refund/,
  )
  assert.match(
    trackingGuidance(fixtureOrders('refund')[0]),
    /No automatic refund/,
  )
  for (const example of ['expired', 'fee_changed'] as const)
    assert.match(
      trackingGuidance(fixtureOrders(example)[0]),
      /No extra amount is charged/,
    )
})

test('operational projections retain C04 totals/quantities and exclude private fields', () => {
  const order = fixtureOrders('active')[0]
  assert.equal(
    order.total_minor,
    contract.order_after_payment.total.amount_minor,
  )
  assert.deepEqual(
    order.items,
    contract.order_after_payment.items.map(({ display_name, quantity }) => ({
      display_name,
      quantity,
    })),
  )
  const markup = renderToStaticMarkup(
    createElement(TrackingOrderDetails, {
      order,
      context: clinic,
      onReady() {},
    }),
  )
  assert.match(markup, /25.00/)
  assert.match(markup, /SGT/)
  assert.doesNotMatch(
    markup,
    /Synthetic instruction placeholder|address_line|postal_code|doctor_id|note_id/,
  )
  assert.doesNotMatch(
    JSON.stringify(order),
    /instructions|address_line|postal_code|doctor_id|note_id/,
  )
  assert.match(markup, /Mark medicine ready \(demo\)/)
  const patientMarkup = renderToStaticMarkup(
    createElement(TrackingOrderDetails, {
      order,
      context: patient,
      onReady() {},
    }),
  )
  assert.doesNotMatch(
    patientMarkup,
    /Mark medicine ready|Simulate readiness action error/,
  )
})

test('all examples render independent snapshots; errors/empty/loading have no synthetic order rows', () => {
  for (const example of Object.keys(examples) as (keyof typeof examples)[]) {
    const orders = fixtureOrders(example)
    if (['loading', 'empty', 'error'].includes(example))
      assert.deepEqual(orders, [])
    for (const order of orders)
      assert.doesNotThrow(() =>
        renderToStaticMarkup(
          createElement(TrackingOrderDetails, {
            order,
            context: patient,
            onReady() {},
          }),
        ),
      )
  }
  const changed = markReady(fixtureOrders('active')[0], clinic)
  assert.equal(changed.medicine_status, 'ready')
  assert.equal(fixtureOrders('active')[0].medicine_status, 'not_ready')
  const empty = renderToStaticMarkup(
    createElement(TrackingOrderList, {
      orders: [],
      selectedId: null,
      onSelect() {},
    }),
  )
  assert.match(empty, /No medication orders/)
})

test('page discloses fixture-only operations and selects an owned order without trusting URL success', () => {
  const markup = renderToStaticMarkup(
    createElement(FulfilmentPreview, { role: 'patient' }),
  )
  assert.match(markup, /synthetic data/)
  assert.match(markup, /No live order is changed and no courier is booked/)
  assert.match(markup, /Order details/)
  assert.doesNotMatch(markup, /Mark medicine ready \(demo\)/)
  const clinicMarkup = renderToStaticMarkup(
    createElement(FulfilmentPreview, {
      role: 'clinic_admin',
      tenantId: otherClinic,
    }),
  )
  assert.match(clinicMarkup, /Mark medicine ready \(demo\)/)
  assert.match(clinicMarkup, new RegExp(otherClinic))
})
