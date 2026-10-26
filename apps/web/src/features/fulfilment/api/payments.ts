import { accessToken } from '@/auth/access-token'
import type { Checkout } from '@/features/payments/api'
import { apiFetch } from '@/lib/api'
import { request } from './client'
import type { Order } from './types'

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
