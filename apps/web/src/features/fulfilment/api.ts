import { apiFetch, ApiError } from '../../lib/api'
import type { CursorPage } from '../../lib/api-types'
import { accessToken } from '../clinics/api'
import { paymentDetail } from '../payments/api'
import type { Checkout, Payment } from '../payments/api'
import type { OrderContext, TrackingOrder } from './model'

type Money = { amount_minor: number; currency: 'SGD' }
export type Order = {
  delivery_snapshot?: Delivery | null
  order_id: string
  tenant_id: string
  patient_id: string
  appointment_id: string
  prescription_id: string
  status: TrackingOrder['status']
  medicine_status: TrackingOrder['medicine_status']
  payment_status: TrackingOrder['payment_status']
  payment_id: string | null
  quote_id: string | null
  delivery_id: string | null
  medication_subtotal: Money
  delivery_fee: Money | null
  total: Money | null
  items: {
    prescription_item_id: string
    medication_id: string
    display_name: string
    quantity: number
    unit_price: Money
    line_total: Money
  }[]
  created_at: string
  updated_at: string
}
export type Quote = {
  contact_confirmed: boolean
  quote_id: string
  order_id: string
  tenant_id: string
  status: 'active' | 'accepted' | 'expired' | 'superseded'
  medication_subtotal: Money
  delivery_fee: Money
  total: Money
  expires_at: string
  created_at: string
}
export type Delivery = {
  delivery_id: string
  order_id: string
  tenant_id: string
  status: NonNullable<TrackingOrder['delivery']>['status']
  created_at: string
  updated_at: string
}
export type Destination = {
  address_line: string
  postal_code: string
  country_code: 'SG'
}
export type RecipientContact = { name: string; phone_number: string }
export type DeliveryDetails = {
  quote_id: string | null
  destination: Destination | null
  recipient: RecipientContact | null
}
export type OrderSnapshot = {
  order: Order
  quote: Quote | null
  payment: Payment | null
  delivery: Delivery | null
}

async function request(path: string, init: RequestInit = {}) {
  return apiFetch(`/fulfilment${path}`, {
    ...init,
    accessToken: await accessToken(),
    signal: init.signal ?? AbortSignal.timeout(20000),
  })
}
export async function listOrders(
  tenantId?: string,
  cursor?: string | null,
  signal?: AbortSignal,
  sort: 'oldest' | 'newest' = 'newest',
): Promise<CursorPage<Order>> {
  const params = new URLSearchParams({ limit: '25' })
  params.set('sort', sort)
  if (tenantId) params.set('tenant_id', tenantId)
  if (cursor) params.set('cursor', cursor)
  const page: CursorPage<Order> = await (
    await request(`/orders?${params}`, { signal })
  ).json()
  const items = await Promise.all(
    page.items.map(async (order) => {
      if (!order.delivery_id) return order
      const delivery: Delivery = await (
        await request(`/deliveries/${encodeURIComponent(order.delivery_id)}`, {
          signal,
        })
      ).json()
      if (
        delivery.delivery_id !== order.delivery_id ||
        delivery.order_id !== order.order_id ||
        delivery.tenant_id !== order.tenant_id
      )
        throw new Error('Delivery unavailable.')
      return { ...order, delivery_snapshot: delivery }
    }),
  )
  return { items, next_cursor: page.next_cursor }
}
export async function readOrder(
  id: string,
  signal?: AbortSignal,
): Promise<Order> {
  return (await request(`/orders/${encodeURIComponent(id)}`, { signal })).json()
}
export async function createOrder(
  prescriptionId: string,
  key: string,
): Promise<Order> {
  return (
    await request('/orders', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Idempotency-Key': key },
      body: JSON.stringify({ prescription_id: prescriptionId }),
    })
  ).json()
}
export async function createQuote(
  orderId: string,
  destination: Destination,
  key: string,
  recipient: RecipientContact,
): Promise<Quote> {
  return (
    await request(`/orders/${encodeURIComponent(orderId)}/quotes`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Idempotency-Key': key },
      body: JSON.stringify({ destination, recipient }),
    })
  ).json()
}
export async function readDeliveryDetails(
  orderId: string,
  signal?: AbortSignal,
): Promise<DeliveryDetails> {
  return (
    await request(`/orders/${encodeURIComponent(orderId)}/delivery-details`, {
      signal,
    })
  ).json()
}
export async function readyOrder(id: string): Promise<Order> {
  return (
    await request(`/orders/${encodeURIComponent(id)}/ready`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: '{}',
    })
  ).json()
}

export async function reconcileOrderPayment(id: string): Promise<Order> {
  return (
    await request(`/orders/${encodeURIComponent(id)}/reconcile-payment`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: '{}',
    })
  ).json()
}
export async function medicationCheckout(
  orderId: string,
  quoteId: string,
  key: string,
): Promise<Checkout> {
  return (
    await apiFetch('/billing/medication-checkouts', {
      method: 'POST',
      accessToken: await accessToken(),
      headers: { 'Content-Type': 'application/json', 'Idempotency-Key': key },
      body: JSON.stringify({ order_id: orderId, quote_id: quoteId }),
      signal: AbortSignal.timeout(20000),
    })
  ).json()
}
export function ownsOrder(order: Order, context: OrderContext) {
  return context.role === 'patient'
    ? order.patient_id === context.patientId
    : order.tenant_id === context.tenantId
}
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
export function fulfilmentError(error: unknown) {
  if (error instanceof ApiError && error.code === 'delivery_contact_required')
    return 'Confirm the recipient contact and delivery address with a new quote before payment.'
  if (error instanceof ApiError && error.code === 'medication_unpriced')
    return 'The clinic admin needs to price this prescription before you can order or pay. Try again once pricing is ready.'
  if (error instanceof ApiError && error.status === 422)
    return 'Check the recipient name, Singapore contact number, delivery address and six-digit postal code.'
  if (error instanceof ApiError && error.status === 409)
    return 'The order or quote changed, expired, or has a pending payment. Refresh its status before continuing.'
  return 'Could not verify the order or payment. Check your connection and session, then refresh. Keep the same payment attempt while its outcome is unknown.'
}

export function deliveryQuoteError(error: unknown) {
  if (error instanceof ApiError) {
    if (error.code === 'clinic_location_missing')
      return 'The clinic needs to save its pickup location in Clinic Settings before delivery can be calculated.'
    if (error.code === 'clinic_location_unavailable')
      return 'The clinic pickup location could not be loaded. Try again later or contact the clinic.'
    if (error.code === 'delivery_unavailable')
      return 'Delivery pricing is unavailable. Contact the clinic to check delivery setup, or try again later.'
    if (error.code === 'unsupported_destination')
      return 'Delivery is not available for this postcode. Contact the clinic for supported delivery areas.'
    if (error.status === 401 || error.status === 403)
      return 'Your session could not be verified. Sign in again before calculating delivery.'
    if (error.status === 409 || error.status === 422)
      return fulfilmentError(error)
  }
  return 'Could not calculate delivery and the total. Check your connection and try again with the same address.'
}
