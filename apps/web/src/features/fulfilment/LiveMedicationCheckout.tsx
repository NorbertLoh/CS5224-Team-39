import { useEffect, useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import {
  beginMedicationCheckout,
  canPay,
  canQuote,
  paymentMessage,
} from './checkout'
import { fulfilmentError, reconcileOrderPayment } from './api'
import type { OrderSnapshot } from './api'
import { LiveDestinationForm } from './LiveDestinationForm'
import { consultationPrice } from '../../lib/money'
import { trackingTime } from './model'

export function LiveMedicationCheckout({
  snapshot,
  subject,
  refresh,
}: {
  snapshot: OrderSnapshot
  subject: string
  refresh: () => Promise<OrderSnapshot>
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
  return (
    <section
      className="space-y-4"
      aria-labelledby="medication-checkout-heading"
    >
      <h2 id="medication-checkout-heading" className="text-xl font-semibold">
        {order.payment_status === 'succeeded'
          ? 'Your medicines'
          : 'Review medicines & pay'}
      </h2>
      <ul
        className="space-y-2 rounded-xl border p-4"
        aria-label="Your medicines"
      >
        {order.items.map((item) => (
          <li
            key={item.prescription_item_id}
            className="flex flex-wrap justify-between gap-3 text-sm"
          >
            <span>
              {item.display_name} · Quantity: {item.quantity}
            </span>
            <span>
              {consultationPrice(item.line_total.amount_minor, 'SGD')}
            </span>
          </li>
        ))}
      </ul>
      <dl className="space-y-2 rounded-xl border p-4 text-sm">
        <div className="flex justify-between gap-3">
          <dt>Medication subtotal</dt>
          <dd>
            {consultationPrice(order.medication_subtotal.amount_minor, 'SGD')}
          </dd>
        </div>
        <div className="flex justify-between gap-3">
          <dt>Delivery fee</dt>
          <dd>
            {order.delivery_fee
              ? consultationPrice(order.delivery_fee.amount_minor, 'SGD')
              : 'Awaiting quote'}
          </dd>
        </div>
        <div className="flex justify-between gap-3 font-semibold">
          <dt>Total (SGD)</dt>
          <dd>
            {order.total
              ? consultationPrice(order.total.amount_minor, 'SGD')
              : 'Awaiting quote'}
          </dd>
        </div>
        {quote && (
          <div>
            <dt>Quote deadline</dt>
            <dd>
              {trackingTime(quote.expires_at)}{' '}
              {Date.parse(quote.expires_at) <= now ? '(expired)' : ''}
            </dd>
          </div>
        )}
      </dl>
      {canQuote(snapshot) && (
        <LiveDestinationForm
          orderId={order.order_id}
          subject={subject}
          onRefresh={() => {
            void refresh().catch(() => undefined)
          }}
          onEditingChange={setEditing}
        />
      )}
      <p role="status" className="text-sm">
        {paymentMessage(snapshot)}
      </p>
      {editing && (
        <p className="text-sm">
          Request a new quote to use the edited address before continuing to
          payment.
        </p>
      )}
      {order.payment_id && (
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
      <p className="text-sm text-slate-600">
        Stripe test checkout. Your payment status updates here after
        confirmation.
      </p>
    </section>
  )
}
