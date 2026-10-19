export type PreviewContext =
  | { role: 'patient'; patientId: string }
  | { role: 'clinic_admin'; tenantId: string }
export type DeliveryStatus =
  | 'pending'
  | 'submitted'
  | 'picked_up'
  | 'delivered'
  | 'cancelled'
  | 'failed'
  | 'unknown'
export type TrackingOrder = {
  order_id: string
  tenant_id: string
  patient_id: string
  prescription_id: string
  prescription_status: 'issued' | 'draft' | 'voided'
  label: string
  status:
    | 'awaiting_payment'
    | 'paid'
    | 'submitting'
    | 'dispatched'
    | 'delivered'
    | 'cancelled'
    | 'exception'
  medicine_status: 'not_ready' | 'ready'
  payment_status:
    | 'unpaid'
    | 'pending'
    | 'succeeded'
    | 'refund_required'
    | 'refunded'
  quote_check: 'valid' | 'expired' | 'fee_changed'
  total_minor: number | null
  items: { display_name: string; quantity: number }[]
  delivery: {
    delivery_id: string
    status: DeliveryStatus
    updated_at: string
  } | null
  updated_at: string
}

export const orderLabels: Record<TrackingOrder['status'], string> = {
  awaiting_payment: 'Awaiting payment',
  paid: 'Paid',
  submitting: 'Submitting delivery',
  dispatched: 'Dispatched',
  delivered: 'Delivered',
  cancelled: 'Cancelled',
  exception: 'Needs attention',
}
export const paymentLabels: Record<TrackingOrder['payment_status'], string> = {
  unpaid: 'Unpaid',
  pending: 'Payment pending',
  succeeded: 'Payment confirmed',
  refund_required: 'Refund review required',
  refunded: 'Refunded',
}
export const deliveryLabels: Record<DeliveryStatus, string> = {
  pending: 'Submission pending',
  submitted: 'Courier accepted',
  picked_up: 'Picked up',
  delivered: 'Delivered',
  cancelled: 'Delivery cancelled',
  failed: 'Delivery failed',
  unknown: 'Delivery outcome unknown',
}

export function visibleOrders(
  orders: TrackingOrder[],
  context: PreviewContext,
) {
  return orders.filter((order) =>
    context.role === 'patient'
      ? order.patient_id === context.patientId
      : order.tenant_id === context.tenantId,
  )
}

export function canMarkReady(order: TrackingOrder, context: PreviewContext) {
  return (
    context.role === 'clinic_admin' &&
    order.tenant_id === context.tenantId &&
    order.prescription_status === 'issued' &&
    ['awaiting_payment', 'paid'].includes(order.status) &&
    !['refund_required', 'refunded'].includes(order.payment_status)
  )
}

// Readiness is independent of payment and delivery, including on repeated actions.
export function markReady(
  order: TrackingOrder,
  context: PreviewContext,
): TrackingOrder {
  if (!canMarkReady(order, context) || order.medicine_status === 'ready')
    return order
  return {
    ...order,
    medicine_status: 'ready',
    updated_at: '2026-10-12T03:05:00Z',
  }
}

export function trackingGuidance(order: TrackingOrder, preview = true) {
  if (order.payment_status === 'refund_required')
    return 'Delivery is on hold. Contact the clinic with your order reference for manual refund review. No automatic refund is promised.'
  if (order.payment_status === 'refunded')
    return 'Payment was refunded. This order will not start a new delivery.'
  if (order.delivery?.status === 'unknown')
    return 'The delivery outcome is uncertain. The clinic must reconcile the existing attempt before another submission; do not place a duplicate order.'
  if (order.delivery?.status === 'failed')
    return 'Delivery failed. Contact the clinic to review the existing delivery; no automatic resubmission is promised.'
  if (order.delivery?.status === 'cancelled' || order.status === 'cancelled')
    return 'This order or delivery was cancelled. Contact the clinic about any payment resolution; cancellation does not itself confirm a refund.'
  if (order.delivery?.status === 'delivered')
    return preview
      ? 'Delivery completion is confirmed in this example.'
      : 'Delivery completion is confirmed.'
  if (order.delivery?.status === 'picked_up')
    return 'The courier has picked up the medicine. Delivery is not yet confirmed.'
  if (order.delivery?.status === 'submitted')
    return 'A courier has accepted the delivery. Pickup and completion are not yet confirmed.'
  if (order.status === 'exception' || order.quote_check !== 'valid')
    return 'Delivery needs clinic review because the quote expired or its fee changed. No extra amount is charged automatically.'
  if (order.status === 'submitting' || order.delivery?.status === 'pending')
    return 'Delivery submission is in progress. A courier has not yet been confirmed.'
  if (order.payment_status !== 'succeeded')
    return order.medicine_status === 'ready'
      ? 'Medicine is ready. Delivery is waiting for confirmed payment.'
      : 'Waiting for payment and medicine preparation. Delivery has not started.'
  if (order.medicine_status !== 'ready')
    return 'Payment is confirmed. Waiting for the clinic to prepare the medicine.'
  return 'Payment and medicine readiness are confirmed. Waiting for delivery submission and a valid quote check; no courier is confirmed yet.'
}

export function trackingTime(instant: string) {
  return (
    new Intl.DateTimeFormat('en-SG', {
      timeZone: 'Asia/Singapore',
      dateStyle: 'medium',
      timeStyle: 'short',
    }).format(new Date(instant)) + ' SGT'
  )
}
