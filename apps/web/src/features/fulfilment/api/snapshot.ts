import type { OrderContext } from '@/features/fulfilment/domain/model'
import { readOrder } from '@/features/fulfilment/api/orders'
import { paymentDetail } from '@/features/payments/api'
import { ApiError } from '@/lib/api'
import { ownsOrder } from '../domain/orders'
import { request } from './client'
import type { Delivery, OrderSnapshot, Quote } from './types'

export async function orderSnapshot(
  id: string,
  context: OrderContext,
  signal?: AbortSignal,
): Promise<OrderSnapshot> {
  const order = await readOrder(id, signal)
  if (order.order_id !== id || !ownsOrder(order, context))
    throw new Error('Order unavailable.')
  const [quote, delivery, payment] = await Promise.all([
    order.quote_id
      ? request(`/quotes/${encodeURIComponent(order.quote_id)}`, {
          signal,
        }).then((response) => response.json() as Promise<Quote>)
      : null,
    order.delivery_id
      ? request(`/deliveries/${encodeURIComponent(order.delivery_id)}`, {
          signal,
        }).then((response) => response.json() as Promise<Delivery>)
      : null,
    order.payment_id
      ? paymentDetail(order.payment_id, signal).catch((error) => {
          // A reservation can exist before billing creates its payment row. Never infer failure.
          if (error instanceof ApiError && error.status === 404) return null
          throw error
        })
      : null,
  ])
  if (
    quote &&
    (quote.quote_id !== order.quote_id ||
      quote.order_id !== id ||
      quote.tenant_id !== order.tenant_id)
  )
    throw new Error('Quote unavailable.')
  if (
    delivery &&
    (delivery.delivery_id !== order.delivery_id ||
      delivery.order_id !== id ||
      delivery.tenant_id !== order.tenant_id)
  )
    throw new Error('Delivery unavailable.')
  if (
    payment &&
    (payment.payment_id !== order.payment_id ||
      payment.order_id !== id ||
      payment.quote_id !== order.quote_id ||
      payment.patient_id !== order.patient_id ||
      payment.tenant_id !== order.tenant_id ||
      payment.purpose !== 'medication_delivery')
  )
    throw new Error('Payment unavailable.')
  return { order, quote, delivery, payment }
}
