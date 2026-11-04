import type { OrderSnapshot } from '@/features/fulfilment/api'
import {
  fulfilmentError,
  reconcileOrderPayment,
} from '@/features/fulfilment/api'
import {
  beginMedicationCheckout,
  canPay,
  canQuote,
  paymentMessage,
} from '@/features/fulfilment/checkout/eligibility'
import { LiveDestinationForm } from '@/features/fulfilment/checkout/LiveDestinationForm'
import { MedicationCheckoutSummary } from '@/features/fulfilment/checkout/MedicationCheckoutSummary'
import { consultationPrice } from '@/lib/money'
import { useMutation } from '@tanstack/react-query'
import { useEffect, useState } from 'react'

export function LiveMedicationCheckout({
  snapshot,
  subject,
  refresh,
  compact = false,
}: {
  snapshot: OrderSnapshot
  subject: string
  refresh: () => Promise<OrderSnapshot>
  compact?: boolean
}) {
  const [editing, setEditing] = useState(false)
  const [now, setNow] = useState(Date.now)
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(timer)
  }, [])
  const checkout = useMutation({
    mutationFn: async () => beginMedicationCheckout(subject, await refresh()),
    retry: false,
    onSuccess: (url) => window.location.assign(url),
  })
  const reconcile = useMutation({
    mutationFn: () => reconcileOrderPayment(snapshot.order.order_id),
    retry: false,
    onSuccess: () => {
      void refresh().catch(() => undefined)
    },
  })
  const { order, quote } = snapshot
  const showPaymentGuidance =
    !compact ||
    order.status === 'awaiting_payment' ||
    ['pending', 'refund_required', 'refunded'].includes(order.payment_status) ||
    (snapshot.payment &&
      [
        'pending',
        'failed',
        'refunded',
        'refund_pending',
        'refund_failed',
      ].includes(snapshot.payment.status)) ||
    snapshot.payment?.resolution === 'refund_required' ||
    (snapshot.payment?.status === 'succeeded' &&
      order.payment_status !== 'succeeded')
  const Heading = compact ? 'h4' : 'h2'
  return (
    <section
      className="space-y-4"
      aria-labelledby="medication-checkout-heading"
    >
      <Heading
        id="medication-checkout-heading"
        className={compact ? 'font-semibold' : 'text-xl font-semibold'}
      >
        {compact
          ? 'Medicines & payment'
          : order.payment_status === 'succeeded'
            ? 'Your medicines'
            : 'Review medicines & pay'}
      </Heading>
      <MedicationCheckoutSummary
        snapshot={snapshot}
        now={now}
        compact={compact}
      />
      {(canQuote(snapshot) || quote?.contact_confirmed) && (
        <LiveDestinationForm
          editable={canQuote(snapshot)}
          orderId={order.order_id}
          quoteId={order.quote_id}
          subject={subject}
          onRefresh={refresh}
          onEditingChange={setEditing}
        />
      )}
      {showPaymentGuidance && (
        <p role="status" className="text-sm">
          {paymentMessage(snapshot)}
        </p>
      )}
      {editing && (
        <p className="text-sm">
          Confirm the edited contact and address with a new quote before
          continuing to payment.
        </p>
      )}
      {!compact && order.payment_id && (
        <p className="break-all text-sm">
          Payment reference: {order.payment_id}
        </p>
      )}
      {order.payment_status === 'pending' &&
        quote &&
        Date.parse(quote.expires_at) <= now && (
          <button
            className="rounded-lg border px-4 py-2"
            disabled={reconcile.isPending}
            onClick={() => reconcile.mutate()}
          >
            {reconcile.isPending
              ? 'Checking expired payment...'
              : 'Recheck expired payment'}
          </button>
        )}
      {reconcile.isError && (
        <p role="alert" className="text-sm text-red-700">
          {fulfilmentError(reconcile.error)}
        </p>
      )}
      {canPay(snapshot, now) && (
        <button
          className="rounded-lg bg-slate-900 px-4 py-3 text-white disabled:opacity-50"
          disabled={editing || checkout.isPending}
          onClick={() => checkout.mutate()}
        >
          {checkout.isPending
            ? 'Opening secure checkout...'
            : order.payment_id
              ? 'Resume payment'
              : `Pay ${consultationPrice(quote!.total.amount_minor, 'SGD')}`}
        </button>
      )}
      {checkout.isError && (
        <p role="alert" className="text-sm text-red-700">
          {fulfilmentError(checkout.error)}
        </p>
      )}
      {(!compact ||
        canPay(snapshot, now) ||
        canQuote(snapshot) ||
        order.payment_status === 'pending') && (
        <p className="text-sm text-slate-600">
          Your payment status updates here after confirmation.
        </p>
      )}
    </section>
  )
}
