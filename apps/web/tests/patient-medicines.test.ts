import assert from 'node:assert/strict'
import { test } from 'node:test'
import { createElement } from 'react'
import contract from '../../../contracts/examples/prescription-order-quote.json'
import type { Order } from '../src/features/fulfilment/api'
import type { OrderSnapshot } from '../src/features/fulfilment/api'
import { LiveMedicationCheckout } from '../src/features/fulfilment/LiveMedicationCheckout'
import type { Prescription } from '../src/features/records/types'
import { PatientMedicationCard } from '../src/features/records/PatientMedicationCard'
import {
  medicineProgress,
  openPrescriptionOrder,
  patientMedicationOrders,
} from '../src/features/fulfilment/patientMedicines'
import { schedulingClient, renderScheduling } from './scheduling-helpers'

const prescription: Prescription = {
  ...contract.prescription,
  status: 'issued',
}
const order = contract.order_after_payment as Order

test('dashboard shows medicines and a direct review action; draft, empty and uncertain records do not prompt payment', () => {
  const client = schedulingClient()
  const render = (props = {}) =>
    renderScheduling(
      client,
      createElement(PatientMedicationCard, {
        prescription,
        checking: false,
        unavailable: false,
        children: 'Prescription details',
        ...props,
      }),
    )
  try {
    const ready = render()
    assert.match(ready, /Your prescribed medicines are ready to order/)
    assert.match(ready, /Review medicines &amp; pay/)
    assert.match(ready, new RegExp(prescription.items[0].display_name))
    assert.match(ready, /Quantity:/)
    assert.match(ready, /separately from your consultation/)
    for (const props of [
      { prescription: { ...prescription, status: 'draft' } },
      { prescription: { ...prescription, items: [] } },
      { checking: true },
      { unavailable: true },
      { order: { ...order, payment_status: 'pending' } },
      { order: { ...order, status: 'delivered', payment_status: 'succeeded' } },
    ])
      assert.doesNotMatch(render(props), /Review medicines &amp; pay/)
    assert.match(
      render({
        order: { ...order, status: 'delivered', payment_status: 'succeeded' },
      }),
      /View delivery details/,
    )
    assert.match(
      render({ order: { ...order, payment_status: 'pending' } }),
      /Check payment status/,
    )
  } finally {
    client.clear()
  }
})

test('review shows medicine line prices and full total before an amount-labelled pay action; paid orders have no pay action', () => {
  const client = schedulingClient()
  const snapshot: OrderSnapshot = {
    order: {
      ...order,
      status: 'awaiting_payment',
      payment_status: 'unpaid',
      payment_id: null,
    },
    quote: {
      ...contract.accepted_quote,
      status: 'active',
      medication_subtotal: order.medication_subtotal,
      delivery_fee: order.delivery_fee!,
      total: order.total!,
      expires_at: new Date(Date.now() + 600000).toISOString(),
    },
    payment: null,
    delivery: null,
  }
  const render = () =>
    renderScheduling(
      client,
      createElement(LiveMedicationCheckout, {
        snapshot,
        subject: order.patient_id,
        refresh: async () => snapshot,
      }),
    )
  try {
    const html = render()
    assert.match(html, /aria-label="Your medicines"/)
    assert.match(html, /Medication subtotal/)
    assert.match(html, /Delivery fee/)
    assert.match(html, /Total \(SGD\)/)
    assert.match(html, />Pay /)
    snapshot.order = { ...order, status: 'paid', payment_status: 'succeeded' }
    assert.doesNotMatch(render(), />Pay |Review medicines &amp; pay/)
  } finally {
    client.clear()
  }
})

test('progress follows confirmed payment and courier facts, including exceptions', () => {
  assert.equal(medicineProgress(), 'Ready to order')
  assert.equal(
    medicineProgress({ ...order, payment_status: 'pending' }),
    'Confirming payment',
  )
  assert.equal(
    medicineProgress({
      ...order,
      payment_status: 'succeeded',
      medicine_status: 'not_ready',
      status: 'paid',
    }),
    'Preparing medicines',
  )
  assert.equal(
    medicineProgress({
      ...order,
      payment_status: 'succeeded',
      medicine_status: 'ready',
      status: 'paid',
    }),
    'Arranging delivery',
  )
  const delivery = {
    delivery_id: 'd',
    order_id: order.order_id,
    tenant_id: order.tenant_id,
    status: 'picked_up' as const,
    created_at: order.created_at,
    updated_at: order.updated_at,
  }
  assert.equal(
    medicineProgress({ ...order, delivery_snapshot: delivery }),
    'Out for delivery',
  )
  assert.equal(
    medicineProgress({
      ...order,
      delivery_snapshot: { ...delivery, status: 'delivered' },
    }),
    'Delivered',
  )
  assert.equal(
    medicineProgress({
      ...order,
      delivery_snapshot: { ...delivery, status: 'failed' },
    }),
    'Contact the clinic',
  )
  assert.equal(
    medicineProgress({ ...order, payment_status: 'refund_required' }),
    'Refund review required',
  )
})

test('direct review reuses its idempotency key, reads current order state, and rejects foreign or unissued records', async (t) => {
  const client = schedulingClient()
  let mode = 'valid'
  const keys: string[] = []
  t.mock.method(
    globalThis,
    'fetch',
    async (path: string, init: RequestInit) => {
      if (path.includes('/prescriptions/'))
        return Response.json({
          ...prescription,
          ...(mode === 'draft' ? { status: 'draft' } : {}),
        })
      if (init.method === 'POST') {
        keys.push(new Headers(init.headers).get('Idempotency-Key')!)
        return Response.json({
          ...order,
          payment_status: 'unpaid',
          ...(mode === 'foreign' ? { tenant_id: 'other' } : {}),
        })
      }
      return Response.json({
        ...order,
        status: 'delivered',
        payment_status: 'succeeded',
      })
    },
  )
  try {
    const first = await openPrescriptionOrder(
      prescription.prescription_id,
      prescription.patient_id,
    )
    const second = await openPrescriptionOrder(
      prescription.prescription_id,
      prescription.patient_id,
    )
    assert.equal(first.status, 'delivered')
    assert.equal(second.order_id, first.order_id)
    assert.equal(keys.length, 2)
    assert.equal(keys[0], keys[1])
    mode = 'draft'
    await assert.rejects(
      openPrescriptionOrder(
        prescription.prescription_id,
        prescription.patient_id,
      ),
    )
    assert.equal(keys.length, 2)
    mode = 'foreign'
    await assert.rejects(
      openPrescriptionOrder(
        prescription.prescription_id,
        prescription.patient_id,
      ),
    )
    mode = 'valid'
    await assert.rejects(
      openPrescriptionOrder(prescription.prescription_id, 'other-patient'),
    )
  } finally {
    client.clear()
  }
})

test('dashboard finds older orders across pages without exposing another patient or accepting looping cursors', async (t) => {
  const client = schedulingClient()
  let cycle = false
  t.mock.method(globalThis, 'fetch', async (path: string) => {
    const cursor = new URL(path, 'http://localhost').searchParams.get('cursor')
    return Response.json({
      items: [
        {
          ...order,
          delivery_id: null,
          patient_id: cursor ? order.patient_id : 'other',
        },
      ],
      next_cursor: cycle || !cursor ? 'next-page' : null,
    })
  })
  try {
    assert.equal((await patientMedicationOrders(order.patient_id)).length, 1)
    cycle = true
    await assert.rejects(patientMedicationOrders(order.patient_id))
  } finally {
    client.clear()
  }
})
