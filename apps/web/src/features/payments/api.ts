import { apiFetch } from '../../lib/api'
import { accessToken } from '../clinics/api'
import type { CursorPage } from '../../lib/api-types'
type Money = { amount_minor: number; currency: string }

export type Payment = {
  payment_id: string
  tenant_id: string
  patient_id: string
  purpose: string
  appointment_id: string | null
  order_id: string | null
  quote_id: string | null
  status: string
  resolution: string
  amount: Money
  commission_bps: number
  commission_amount: Money
  clinic_amount: Money
  created_at: string
  updated_at: string
}
export type Totals = {
  payment_count: number
  amount: Money
  commission_amount: Money
  clinic_amount: Money
}
export type Refund = {
  refund_id: string
  payment_id: string
  requested_by: string
  requested_by_name: string
  reason: string
  status: 'pending' | 'succeeded' | 'failed' | 'review'
  created_at: string
  updated_at: string
  last_error: string | null
  retry_allowed: boolean
}

export async function refundHistory(
  id: string,
  signal?: AbortSignal,
): Promise<Refund[]> {
  return (
    await request(`/payments/${encodeURIComponent(id)}/refunds`, { signal })
  ).json()
}

export async function refundPayment(
  id: string,
  reason: string,
): Promise<Refund> {
  return (
    await request(`/payments/${encodeURIComponent(id)}/refunds`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ reason }),
    })
  ).json()
}
export type Checkout = {
  payment: Payment
  checkout_url: string
  expires_at: string
}

async function request(path: string, init: RequestInit = {}) {
  return apiFetch(`/billing${path}`, {
    ...init,
    accessToken: await accessToken(),
    signal: init.signal ?? AbortSignal.timeout(15000),
  })
}
export async function paymentDetail(
  id: string,
  signal?: AbortSignal,
): Promise<Payment> {
  return (
    await request(`/payments/${encodeURIComponent(id)}`, { signal })
  ).json()
}
export async function listPayments(
  tenantId: string,
  purpose = 'all',
  status = 'all',
  cursor?: string | null,
  signal?: AbortSignal,
): Promise<CursorPage<Payment>> {
  const query = new URLSearchParams({ tenant_id: tenantId, limit: '25' })
  if (purpose !== 'all') query.set('purpose', purpose)
  if (status !== 'all') query.set('status', status)
  if (cursor) query.set('cursor', cursor)
  return (await request(`/payments?${query}`, { signal })).json()
}
export async function paymentTotals(
  tenantId: string,
  purpose = 'all',
  signal?: AbortSignal,
): Promise<Totals> {
  const query = new URLSearchParams({ tenant_id: tenantId })
  if (purpose !== 'all') query.set('purpose', purpose)
  return (await request(`/commission-totals?${query}`, { signal })).json()
}
export async function createCheckout(
  appointmentId: string,
  key: string,
): Promise<Checkout> {
  return (
    await request('/consultation-checkouts', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Idempotency-Key': key },
      body: JSON.stringify({ appointment_id: appointmentId }),
    })
  ).json()
}

export function stripeCheckoutUrl(checkout: Checkout, now = Date.now()) {
  const url = new URL(checkout.checkout_url)
  if (
    url.protocol !== 'https:' ||
    url.hostname !== 'checkout.stripe.com' ||
    url.port ||
    url.username ||
    url.password ||
    !Number.isFinite(Date.parse(checkout.expires_at)) ||
    Date.parse(checkout.expires_at) <= now
  )
    throw new Error('Checkout is expired or unavailable. Refresh your booking.')
  return url.href
}
