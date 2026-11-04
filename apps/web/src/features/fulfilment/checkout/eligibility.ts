import type { OrderSnapshot } from '@/features/fulfilment/api'
import { medicationCheckout } from '@/features/fulfilment/api'
import { stripeCheckoutUrl } from '@/features/payments/api'

export function canQuote({ order, payment }: OrderSnapshot) {
  return (
    order.status === 'awaiting_payment' &&
    !['succeeded', 'refund_required', 'refunded'].includes(
      order.payment_status,
    ) &&
    ((!order.payment_id && order.payment_status === 'unpaid') ||
      payment?.status === 'failed')
  )
}
export function canPay(snapshot: OrderSnapshot, now = Date.now()) {
  const { order, quote, payment } = snapshot
  return (
    order.status === 'awaiting_payment' &&
    !['succeeded', 'refund_required', 'refunded'].includes(
      order.payment_status,
    ) &&
    quote !== null &&
    (quote.contact_confirmed || Boolean(order.payment_id)) &&
    ['active', 'accepted'].includes(quote.status) &&
    Date.parse(quote.expires_at) > now &&
    (!payment || ['pending', 'failed'].includes(payment.status)) &&
    payment?.resolution !== 'refund_required'
  )
}
export function stableKey(
  storage: Storage,
  scope: string,
  attempt = 'initial',
) {
  const raw = storage.getItem(scope)
  const saved = raw
    ? (JSON.parse(raw) as { key: string; attempt: string })
    : null
  if (saved?.attempt === attempt) return saved.key
  const key = crypto.randomUUID()
  storage.setItem(scope, JSON.stringify({ key, attempt }))
  return key
}
export async function beginMedicationCheckout(
  subject: string,
  snapshot: OrderSnapshot,
  storage: Storage = sessionStorage,
) {
  if (snapshot.order.patient_id !== subject || !canPay(snapshot))
    throw new Error('Order is not payable.')
  const { order, quote, payment } = snapshot
  const scope = `telelink.medication-checkout.${subject}.${order.order_id}.${quote!.quote_id}`
  if (order.payment_id && !payment && !storage.getItem(scope))
    throw new Error(
      'The existing payment needs reconciliation. Refresh its status.',
    )
  const saved = storage.getItem(scope)
  const priorAttempt = saved
    ? (JSON.parse(saved) as { attempt: string }).attempt
    : 'initial'
  const key = stableKey(
    storage,
    scope,
    payment?.status === 'failed' ? payment.payment_id : priorAttempt,
  )
  storage.setItem(`telelink.medication-return.${subject}`, order.order_id)
  const checkout = await medicationCheckout(
    order.order_id,
    quote!.quote_id,
    key,
  )
  const result = checkout.payment
  if (
    result.order_id !== order.order_id ||
    result.quote_id !== quote!.quote_id ||
    result.patient_id !== subject ||
    result.tenant_id !== order.tenant_id ||
    result.purpose !== 'medication_delivery' ||
    result.amount.currency !== 'SGD' ||
    result.amount.amount_minor !== quote!.total.amount_minor ||
    (order.payment_id &&
      payment?.status !== 'failed' &&
      result.payment_id !== order.payment_id)
  )
    throw new Error('Checkout context is unavailable.')
  return stripeCheckoutUrl(checkout)
}
export function paymentMessage({ order, payment }: OrderSnapshot) {
  if (
    order.payment_status === 'refund_required' ||
    payment?.resolution === 'refund_required'
  )
    return 'Manual refund review required. Contact the clinic with your order and payment references. No automatic refund is promised.'
  if (payment?.status === 'refunded' || order.payment_status === 'refunded')
    return 'Payment refunded. This order will not start a new delivery.'
  if (payment?.status === 'succeeded')
    return order.payment_status === 'succeeded'
      ? 'Medication payment confirmed. Delivery still depends on medicine readiness and verified courier status.'
      : 'Payment received; waiting for the order to confirm it. Do not start another payment.'
  if (payment && ['refund_pending', 'refund_failed'].includes(payment.status))
    return 'Refund processing or review is pending. Contact the clinic; do not start another payment.'
  if (payment?.status === 'failed')
    return 'The previous payment failure is verified. Obtain a fresh quote or retry before the quote deadline.'
  if (order.payment_id)
    return 'Payment pending or awaiting reconciliation. Returning from Stripe does not confirm success or failure. Check this attempt before starting another payment.'
  return 'Confirm your delivery contact and address, review the full total, then pay securely.'
}
