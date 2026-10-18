import contract from '../../../../../contracts/examples/booking-payment.json'
import type { CheckoutSnapshot } from './status'

// Frozen server time keeps these historical contract examples repeatable.
export const fixtureNow = Date.parse('2026-10-12T03:00:00Z')
const pending: CheckoutSnapshot = {
  payment: 'pending',
  appointment: 'pending_payment',
  resolution: 'awaiting_payment',
  holdExpiresAt: '2026-10-12T03:05:00Z',
}
export const checkoutSummary = {
  appointmentId: contract.appointment.appointment_id,
  paymentId: contract.payment.payment_id,
  startsAt: contract.appointment.starts_at,
  amount: contract.payment.amount,
}
export const scenarios = {
  return: { label: 'Provider return', snapshot: pending },
  pending: { label: 'Payment pending', snapshot: pending },
  failed: {
    label: 'Payment failed',
    snapshot: { ...pending, payment: 'failed' },
  },
  cancelled: {
    label: 'Checkout cancelled (payment still pending)',
    snapshot: pending,
  },
  success: {
    label: 'Payment and booking confirmed',
    snapshot: {
      ...pending,
      payment: 'succeeded',
      appointment: 'confirmed',
      resolution: 'confirmed',
      holdExpiresAt: null,
    },
  },
  confirming: {
    label: 'Paid, awaiting booking confirmation',
    snapshot: { ...pending, payment: 'succeeded' },
  },
  expired: {
    label: 'Hold expired',
    snapshot: { ...pending, appointment: 'expired' },
  },
  recovered: {
    label: 'Late payment: booking recovered',
    snapshot: {
      ...pending,
      payment: 'succeeded',
      appointment: 'confirmed',
      resolution: 'confirmed',
      holdExpiresAt: null,
    },
  },
  refund: {
    label: 'Late payment: slot unavailable',
    snapshot: {
      ...pending,
      payment: 'succeeded',
      appointment: 'expired',
      resolution: 'refund_required',
    },
  },
  refundPending: {
    label: 'Refund processing',
    snapshot: {
      ...pending,
      payment: 'refund_pending',
      appointment: 'cancelled',
      resolution: 'refund_required',
    },
  },
  refunded: {
    label: 'Refund completed',
    snapshot: {
      ...pending,
      payment: 'refunded',
      appointment: 'cancelled',
      resolution: 'refunded',
    },
  },
  error: { label: 'Status unavailable', snapshot: null },
  missing: { label: 'Missing payment reference', snapshot: null },
} satisfies Record<string, { label: string; snapshot: CheckoutSnapshot | null }>
export type Scenario = keyof typeof scenarios
