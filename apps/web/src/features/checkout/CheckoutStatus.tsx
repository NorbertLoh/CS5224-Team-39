import { consultationPrice } from '../../lib/money'
import type { CheckoutState } from './status'

const messages: Record<
  CheckoutState | 'ready' | 'return' | 'error' | 'missing',
  [string, string]
> = {
  ready: [
    'Ready for payment',
    'Your booking is held until its original deadline. Continue to secure checkout to pay the consultation fee.',
  ],
  no_show: [
    'Appointment marked no-show',
    'Contact the clinic about this booking. Review the payment details below before making another booking.',
  ],
  return: [
    'Welcome back from checkout',
    'Your return does not confirm payment. Check the payment and booking status before trying again.',
  ],
  pending: [
    'Payment pending',
    'Payment has not been confirmed. Continue to secure checkout to resume your existing payment.',
  ],
  failed: [
    'Payment unsuccessful',
    'This payment attempt failed. You can retry while the original booking hold is valid.',
  ],
  success: [
    'Appointment confirmed',
    'Payment received and your consultation is confirmed. You can find the booking in Appointments.',
  ],
  confirming: [
    'Payment received, confirming appointment',
    'Your payment succeeded. We are waiting for the booking confirmation. Do not pay again.',
  ],
  expired: [
    'Booking hold expired',
    'This time is no longer reserved. Browse clinics to choose another appointment.',
  ],
  cancelled: [
    'Booking cancelled',
    'This appointment is cancelled. Check payment status before making another booking.',
  ],
  refund_required: [
    'Payment received, booking not confirmed',
    'Your payment requires refund review. Contact the clinic with the references below. The clinic admin can review and issue a refund. Do not pay again for this booking.',
  ],
  refund_pending: [
    'Refund processing',
    'The booking is not confirmed. A refund has been requested; check again for completion.',
  ],
  refunded: [
    'Payment refunded',
    'The payment has been refunded. This booking is not confirmed.',
  ],
  error: [
    'Unable to check payment status',
    'The payment outcome is unknown. Try checking again; do not make another payment.',
  ],
  missing: [
    'Payment reference unavailable',
    'We cannot identify this checkout. Open Appointments or contact the clinic before trying another payment.',
  ],
}

export function CheckoutStatus({
  state,
  summary,
  busy = false,
  cancelledReturn = false,
  onCheck,
  onRetry,
}: {
  summary?: {
    appointmentId: string
    paymentId: string | null
    startsAt: string
    clinicName: string
    doctorName: string
    expiresAt?: string | null
    amount: { amount_minor: number; currency: string }
  }
  busy?: boolean
  state: keyof typeof messages
  cancelledReturn?: boolean
  onCheck: () => void
  onRetry: () => void
}) {
  const [title, description] = messages[state]
  return (
    <section
      className="rounded-2xl border bg-white p-6 sm:p-8"
      aria-labelledby="checkout-title"
    >
      <div role="status" aria-live="polite">
        <h1 id="checkout-title" className="text-2xl font-semibold">
          {title}
        </h1>
        <p className="mt-3 leading-relaxed text-slate-600">{description}</p>
        {cancelledReturn && (
          <p className="mt-3 text-sm">
            You left checkout. This alone does not mean the payment failed or
            the booking was cancelled.
          </p>
        )}
      </div>
      {summary && (
        <dl className="my-6 space-y-3 rounded-xl bg-slate-50 p-4 text-sm">
          <div>
            <dt className="text-slate-500">Clinic</dt>
            <dd>{summary.clinicName}</dd>
          </div>
          <div>
            <dt className="text-slate-500">Doctor</dt>
            <dd>{summary.doctorName}</dd>
          </div>
          <div>
            <dt className="text-slate-500">Consultation</dt>
            <dd>
              {new Date(summary.startsAt).toLocaleString('en-SG', {
                timeZone: 'Asia/Singapore',
              })}{' '}
              SGT
            </dd>
          </div>
          <div>
            <dt className="text-slate-500">Total</dt>
            <dd>
              {consultationPrice(
                summary.amount.amount_minor,
                summary.amount.currency,
              )}
            </dd>
          </div>
          {summary.expiresAt && (
            <div>
              <dt className="text-slate-500">Booking hold expires</dt>
              <dd>
                {new Date(summary.expiresAt).toLocaleString('en-SG', {
                  timeZone: 'Asia/Singapore',
                })}{' '}
                SGT
              </dd>
            </div>
          )}
          <div>
            <dt className="text-slate-500">Appointment reference</dt>
            <dd className="break-all">{summary.appointmentId}</dd>
          </div>
          {summary.paymentId && (
            <div>
              <dt className="text-slate-500">Payment reference</dt>
              <dd className="break-all">{summary.paymentId}</dd>
            </div>
          )}
        </dl>
      )}
      <div className="mt-6 flex flex-wrap gap-3">
        {(state === 'ready' || state === 'pending') && (
          <button
            type="button"
            className="rounded-lg bg-slate-900 px-4 py-3 text-white"
            disabled={busy}
            onClick={onRetry}
          >
            Continue to secure checkout
          </button>
        )}
        {state !== 'missing' &&
          state !== 'ready' &&
          state !== 'pending' &&
          state !== 'confirming' &&
          state !== 'success' &&
          state !== 'expired' && (
            <button
              type="button"
              className="rounded-lg bg-slate-900 px-4 py-3 text-white"
              disabled={busy}
              onClick={onCheck}
            >
              Check payment status
            </button>
          )}
        {state === 'failed' && (
          <button
            type="button"
            className="rounded-lg border px-4 py-3"
            disabled={busy}
            onClick={onRetry}
          >
            Retry payment
          </button>
        )}
        {!['ready', 'pending', 'expired', 'confirming', 'success'].includes(state) && (
          <a className="rounded-lg border px-4 py-3" href="/patient">
            Appointments
          </a>
        )}
        {(state === 'expired' || state === 'refunded') && (
          <a className="rounded-lg border px-4 py-3" href="/">
            Browse clinics
          </a>
        )}
      </div>
    </section>
  )
}
