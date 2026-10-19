import contract from '../../../../../contracts/examples/prescription-order-quote.json'
import type { Dispatch } from 'react'
import type { Action, OrderState, Outcome, PaymentState } from './model'

export const paymentOutcomes: Record<Outcome, string> = {
  pending: 'Payment still pending',
  cancelled: 'Checkout cancelled, status still pending',
  unknown: 'Status unavailable',
  failed: 'Payment failure verified',
  confirming: 'Payment succeeded, order update pending',
  paid: 'Payment and order confirmed',
  refund_required: 'Late payment requires manual refund review',
}
const messages: Record<
  Exclude<PaymentState, 'none'>,
  { title: string; text: string }
> = {
  pending: {
    title: 'Payment pending',
    text: 'Do not start another payment. Check the current attempt for an updated result.',
  },
  unknown: {
    title: 'Payment status unavailable',
    text: 'The outcome is unknown. Keep this payment reference and check again before making another attempt.',
  },
  failed: {
    title: 'Payment failed',
    text: 'The demo payment failure is verified. Retry before the quote deadline, or request a fresh quote.',
  },
  confirming: {
    title: 'Payment received, order update pending',
    text: 'Wait for the order to confirm payment. Do not start another payment.',
  },
  paid: {
    title: 'Medication payment confirmed',
    text: 'The order is paid and waiting for the clinic to prepare the medicine. Payment alone does not confirm dispatch or delivery.',
  },
  refund_required: {
    title: 'Manual refund review required',
    text: 'Payment arrived after the quote deadline in this example. Contact the clinic with your order and payment references. Delivery is on hold; no automatic refund is promised.',
  },
}

export function MedicationPayment({
  state,
  outcome,
  dispatch,
}: {
  state: OrderState
  outcome: Outcome
  dispatch: Dispatch<Action>
}) {
  if (state.payment === 'none') return null
  const message = messages[state.payment]
  const checkable = ['pending', 'unknown', 'confirming'].includes(state.payment)
  return (
    <section
      className="space-y-3 rounded-xl border bg-slate-50 p-5"
      aria-labelledby="medication-payment-heading"
    >
      <div role="status" className="space-y-2">
        <h2 id="medication-payment-heading" className="text-xl font-semibold">
          {message.title}
        </h2>
        <p className="text-sm">{message.text}</p>
        {state.cancelledReturn && (
          <p className="text-sm">
            Returning from cancelled checkout does not mean payment failed. The
            attempt remains pending until verified.
          </p>
        )}
      </div>
      <p className="text-sm">
        Payment reference:{' '}
        <span className="break-all">
          {contract.medication_payment.payment_id}
        </span>
      </p>
      {checkable && (
        <button
          className="rounded-lg border bg-white px-4 py-2"
          onClick={() => dispatch({ type: 'check', outcome })}
        >
          Check demo payment status
        </button>
      )}
    </section>
  )
}
