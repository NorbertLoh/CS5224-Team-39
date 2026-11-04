import type { TrackingOrder } from '@/features/fulfilment/domain/model'
import type { Delivery, Order } from '../api/types'

export function trackingOrder(
  order: Order,
  delivery: Delivery | null = order.delivery_snapshot ?? null,
): TrackingOrder {
  return {
    order_id: order.order_id,
    tenant_id: order.tenant_id,
    patient_id: order.patient_id,
    prescription_id: order.prescription_id,
    prescription_status: 'issued',
    label: `Order ${order.order_id.slice(-8)}`,
    status: order.status,
    medicine_status: order.medicine_status,
    payment_status: order.payment_status,
    quote_check: 'valid',
    total_minor: order.total?.amount_minor ?? null,
    items: order.items,
    delivery,
    updated_at: order.updated_at,
  }
}
