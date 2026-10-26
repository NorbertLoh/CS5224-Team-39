import type { Order } from '@/features/fulfilment/api'
import { createOrder, listOrders, readOrder } from '@/features/fulfilment/api'
import { stableKey } from '@/features/fulfilment/checkout/eligibility'
import { readPrescription } from '@/features/records/api'
import type { Prescription } from '@/features/records/types'

export async function patientMedicationOrders(
  subject: string,
  signal?: AbortSignal,
) {
  const orders: Order[] = []
  const seen = new Set<string>()
  let cursor: string | null = null
  for (let pageNumber = 0; pageNumber < 100; pageNumber++) {
    const page = await listOrders(undefined, cursor, signal)
    orders.push(...page.items.filter((order) => order.patient_id === subject))
    cursor = page.next_cursor
    if (!cursor) return orders
    if (seen.has(cursor)) break
    seen.add(cursor)
  }
  throw new Error('Medication orders unavailable.')
}

export async function openPrescriptionOrder(
  prescriptionId: string,
  subject: string,
  storage: Storage = sessionStorage,
) {
  const prescription = await readPrescription(prescriptionId)
  if (
    prescription.prescription_id !== prescriptionId ||
    prescription.patient_id !== subject ||
    prescription.status !== 'issued' ||
    prescription.items.length === 0
  )
    throw new Error('Issued prescription unavailable.')
  const key = stableKey(storage, `telelink.order.${subject}.${prescriptionId}`)
  const created = await createOrder(prescriptionId, key)
  assertOrderContext(created, prescription)
  // A replayed POST can contain an old snapshot, so always open the current order.
  const current = await readOrder(created.order_id)
  if (current.order_id !== created.order_id)
    throw new Error('Order unavailable.')
  assertOrderContext(current, prescription)
  return current
}

function assertOrderContext(order: Order, prescription: Prescription) {
  if (
    order.prescription_id !== prescription.prescription_id ||
    order.patient_id !== prescription.patient_id ||
    order.tenant_id !== prescription.tenant_id ||
    order.appointment_id !== prescription.appointment_id
  )
    throw new Error('Order unavailable.')
}

export function medicineProgress(order?: Order) {
  if (!order) return 'Ready to order'
  if (order.payment_status === 'refund_required')
    return 'Refund review required'
  if (order.payment_status === 'refunded') return 'Payment refunded'
  if (
    order.status === 'cancelled' ||
    order.delivery_snapshot?.status === 'cancelled'
  )
    return 'Order cancelled'
  if (
    order.status === 'exception' ||
    ['failed', 'unknown'].includes(order.delivery_snapshot?.status ?? '')
  )
    return 'Contact the clinic'
  if (order.payment_status === 'pending') return 'Confirming payment'
  if (order.payment_status !== 'succeeded') return 'Awaiting payment'
  if (
    order.status === 'delivered' ||
    order.delivery_snapshot?.status === 'delivered'
  )
    return 'Delivered'
  if (order.delivery_snapshot?.status === 'picked_up') return 'Out for delivery'
  if (order.delivery_snapshot?.status === 'submitted') return 'Courier assigned'
  if (order.medicine_status === 'ready') return 'Arranging delivery'
  return 'Preparing medicines'
}

export function canReviewMedicinePayment(order?: Order) {
  return (
    !order ||
    (order.status === 'awaiting_payment' &&
      order.payment_status === 'unpaid' &&
      !order.payment_id)
  )
}
