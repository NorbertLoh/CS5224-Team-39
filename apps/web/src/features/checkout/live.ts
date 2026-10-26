import type { CheckoutSnapshot } from '@/features/checkout/status'
import { checkoutState } from '@/features/checkout/status'
import type { Payment } from '@/features/payments/api'
import { createCheckout, stripeCheckoutUrl } from '@/features/payments/api'
import type { Appointment } from '@/features/scheduling/api'

export const billingError =
  'Could not verify billing. Check your connection and session, then refresh the status. Do not start another payment while the outcome is unknown.'

export function liveCheckoutState(
  appointment: Appointment,
  payment: Payment | null,
  now = Date.now(),
) {
  if (
    payment &&
    (payment.appointment_id !== appointment.appointment_id ||
      payment.patient_id !== appointment.patient_id ||
      payment.tenant_id !== appointment.tenant_id ||
      payment.purpose !== 'consultation' ||
      payment.payment_id !== appointment.payment_id)
  )
    throw new Error('Payment does not match booking.')
  if (
    payment &&
    ![
      'pending',
      'failed',
      'succeeded',
      'refund_pending',
      'refunded',
      'refund_failed',
    ].includes(payment.status)
  )
    throw new Error('Unknown payment status.')
  if (Boolean(appointment.payment_id) !== Boolean(payment))
    throw new Error('Payment reference unavailable.')
  return checkoutState(
    {
      payment: (payment?.status ?? 'pending') as CheckoutSnapshot['payment'],
      appointment: appointment.status,
      resolution:
        payment?.resolution === 'refund_required'
          ? 'refund_required'
          : appointment.payment_resolution === 'none'
            ? 'awaiting_payment'
            : appointment.payment_resolution,
      holdExpiresAt: appointment.hold_expires_at,
    },
    now,
  )
}

export function canCheckout(
  appointment: Appointment,
  payment: Payment | null,
  now = Date.now(),
) {
  return (
    (appointment.status === 'held' ||
      appointment.status === 'pending_payment') &&
    Boolean(
      appointment.hold_expires_at &&
        Date.parse(appointment.hold_expires_at) > now,
    ) &&
    (!payment || payment.status === 'pending' || payment.status === 'failed') &&
    appointment.payment_resolution !== 'refund_required' &&
    payment?.resolution !== 'refund_required'
  )
}

// Persist before sending: a reload or timeout must reuse the same request key.
export async function beginCheckout(
  subject: string,
  appointment: Appointment,
  payment: Payment | null,
  storage: Storage = sessionStorage,
) {
  liveCheckoutState(appointment, payment)
  if (appointment.patient_id !== subject || !canCheckout(appointment, payment))
    throw new Error('Booking is not payable.')
  const storageKey = `telelink.checkout.${subject}.${appointment.appointment_id}`
  const previous = storage.getItem(storageKey)
  // A fresh key is allowed only after an authoritative failed payment read.
  const failedPayment = payment?.status === 'failed' ? payment.payment_id : null
  let saved: { key: string; attempt: string } | null = null
  if (previous) saved = JSON.parse(previous)
  const attempt = failedPayment ?? saved?.attempt ?? 'initial'
  const key = saved?.attempt === attempt ? saved.key : crypto.randomUUID()
  storage.setItem(storageKey, JSON.stringify({ key, attempt }))
  storage.setItem(
    `telelink.checkout-return.${subject}`,
    appointment.appointment_id,
  )
  const checkout = await createCheckout(appointment.appointment_id, key)
  if (
    checkout.payment.appointment_id !== appointment.appointment_id ||
    checkout.payment.patient_id !== subject ||
    checkout.payment.tenant_id !== appointment.tenant_id
  )
    throw new Error('Checkout does not match booking.')
  return stripeCheckoutUrl(checkout)
}
