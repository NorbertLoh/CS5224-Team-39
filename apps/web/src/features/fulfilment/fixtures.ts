import contract from '../../../../../contracts/examples/prescription-order-quote.json'
import type { TrackingOrder } from './model'

export const demoPatientId = contract.order_after_payment.patient_id
export const demoTenantId = contract.order_after_payment.tenant_id
const source = contract.order_after_payment
const base: TrackingOrder = {
  order_id: source.order_id,
  tenant_id: source.tenant_id,
  patient_id: source.patient_id,
  prescription_id: source.prescription_id,
  prescription_status: 'issued',
  label: 'Demo order 001',
  status: 'paid',
  medicine_status: 'not_ready',
  payment_status: 'succeeded',
  quote_check: 'valid',
  total_minor: source.total.amount_minor,
  items: source.items.map(({ display_name, quantity }) => ({
    display_name,
    quantity,
  })),
  delivery: null,
  updated_at: source.updated_at,
}

export const examples = {
  active: 'Active orders',
  submitting: 'Submission pending',
  submitted: 'Courier accepted',
  picked_up: 'Picked up',
  delivered: 'Delivered',
  cancelled: 'Cancelled delivery',
  failed: 'Failed delivery',
  unknown: 'Unknown delivery outcome',
  expired: 'Expired quote',
  fee_changed: 'Delivery fee changed',
  refund: 'Manual refund review',
  refunded: 'Refund completed',
  loading: 'Loading orders',
  empty: 'No orders',
  error: 'Orders unavailable',
}
export type Example = keyof typeof examples

// Clinic previews bind these synthetic examples to the selected clinic context.
// No live order/patient is loaded, and no clinical text or address is projected.
export function fixtureOrders(
  example: Example,
  tenantId = demoTenantId,
): TrackingOrder[] {
  const order = {
    ...base,
    tenant_id: tenantId,
    items: base.items.map((item) => ({ ...item })),
  }
  if (example === 'loading' || example === 'empty' || example === 'error')
    return []
  if (example === 'active')
    return [
      order,
      {
        ...order,
        order_id: '00000000-0000-4000-8000-000000000112',
        prescription_id: '00000000-0000-4000-8000-000000000113',
        label: 'Demo order 002',
        status: 'awaiting_payment',
        payment_status: 'unpaid',
      },
      {
        ...order,
        order_id: '00000000-0000-4000-8000-000000000212',
        prescription_id: '00000000-0000-4000-8000-000000000213',
        label: 'Demo order 003',
        medicine_status: 'ready',
      },
    ]
  if (example === 'expired' || example === 'fee_changed')
    return [
      {
        ...order,
        label: examples[example],
        medicine_status: 'ready',
        status: 'exception',
        quote_check: example,
      },
    ]
  if (example === 'refund' || example === 'refunded')
    return [
      {
        ...order,
        label: examples[example],
        status: example === 'refund' ? 'exception' : 'cancelled',
        payment_status: example === 'refund' ? 'refund_required' : 'refunded',
        quote_check: 'expired',
      },
    ]
  const deliveryStatus = example === 'submitting' ? 'pending' : example
  const status =
    example === 'delivered'
      ? 'delivered'
      : example === 'cancelled'
        ? 'cancelled'
        : example === 'failed'
          ? 'exception'
          : example === 'submitting' || example === 'unknown'
            ? 'submitting'
            : 'dispatched'
  return [
    {
      ...order,
      label: examples[example],
      medicine_status: 'ready',
      status,
      delivery: {
        delivery_id: contract.delivery_later.delivery_id,
        status: deliveryStatus,
        updated_at: contract.delivery_later.updated_at,
      },
      updated_at: contract.delivery_later.updated_at,
    },
  ]
}
