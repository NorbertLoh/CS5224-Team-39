import type { OrderSnapshot } from './api'
import { consultationPrice } from '../../lib/money'
import { trackingTime } from './model'

export function MedicationCheckoutSummary({
  snapshot,
  now,
  compact = false,
}: {
  snapshot: OrderSnapshot
  now: number
  compact?: boolean
}) {
  const { order, quote } = snapshot
  const collapsedPricing =
    compact &&
    order.status !== 'awaiting_payment' &&
    order.payment_status !== 'pending'
  const Pricing = collapsedPricing ? 'details' : 'div'
  return (
    <>
      <ul
        className={
          compact ? 'divide-y text-sm' : 'space-y-2 rounded-xl border p-4'
        }
        aria-label="Your medicines"
      >
        {order.items.map((item) => (
          <li
            key={item.prescription_item_id}
            className="flex flex-wrap justify-between gap-3 py-2 text-sm"
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
      <Pricing className={compact ? 'space-y-3 text-sm' : ''}>
        {collapsedPricing && (
          <summary className="cursor-pointer font-medium">
            Total:{' '}
            {order.total
              ? consultationPrice(order.total.amount_minor, 'SGD')
              : 'Awaiting quote'}{' '}
            · Cost breakdown
          </summary>
        )}
        <dl
          className={
            compact
              ? 'space-y-2 rounded-lg bg-slate-50 p-3 text-sm'
              : 'space-y-2 rounded-xl border p-4 text-sm'
          }
        >
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
          {quote && !collapsedPricing && (
            <div>
              <dt>Quote deadline</dt>
              <dd>
                {trackingTime(quote.expires_at)}{' '}
                {Date.parse(quote.expires_at) <= now ? '(expired)' : ''}
              </dd>
            </div>
          )}
        </dl>
      </Pricing>
    </>
  )
}
