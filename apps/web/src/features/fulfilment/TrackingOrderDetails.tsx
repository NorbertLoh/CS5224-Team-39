import { DeliveryTracking } from './DeliveryTracking'
import { MedicineReadiness } from './MedicineReadiness'
import { orderLabels, paymentLabels, trackingTime } from './model'
import type { PreviewContext, TrackingOrder } from './model'
import { consultationPrice } from '../../lib/money'
import type { ReactNode } from 'react'

export function TrackingOrderDetails({
  order,
  context,
  onReady,
  readiness,
  preview = true,
}: {
  order: TrackingOrder
  context: PreviewContext
  onReady: () => void
  readiness?: ReactNode
  preview?: boolean
}) {
  return (
    <article
      className="space-y-5 rounded-xl border p-5"
      aria-labelledby="tracking-detail-heading"
    >
      <h2 id="tracking-detail-heading" className="text-xl font-semibold">
        Order details
      </h2>
      <dl className="space-y-3 text-sm">
        <div>
          <dt className="font-medium">Order reference</dt>
          <dd className="break-all">{order.order_id}</dd>
        </div>
        <div>
          <dt className="font-medium">Prescription reference</dt>
          <dd className="break-all">{order.prescription_id}</dd>
        </div>
        <div>
          <dt className="font-medium">Order status</dt>
          <dd>{orderLabels[order.status]}</dd>
        </div>
        <div>
          <dt className="font-medium">Payment</dt>
          <dd>{paymentLabels[order.payment_status]}</dd>
        </div>
        <div>
          <dt className="font-medium">Medicine</dt>
          <dd>{order.medicine_status === 'ready' ? 'Ready' : 'Not ready'}</dd>
        </div>
        <div>
          <dt className="font-medium">Total (SGD)</dt>
          <dd>
            {order.total_minor === null
              ? 'Awaiting quote'
              : consultationPrice(order.total_minor, 'SGD')}
          </dd>
        </div>
        <div>
          <dt className="font-medium">Order updated</dt>
          <dd>{trackingTime(order.updated_at)}</dd>
        </div>
      </dl>
      <section aria-labelledby="dispensing-items-heading" className="space-y-2">
        <h3 id="dispensing-items-heading" className="font-semibold">
          Order items
        </h3>
        <ul className="space-y-2 text-sm">
          {order.items.map((item, index) => (
            <li key={index}>
              {item.display_name} · {item.quantity} dispensing units
            </li>
          ))}
        </ul>
      </section>
      {readiness ?? (
        <MedicineReadiness order={order} context={context} onReady={onReady} />
      )}
      <DeliveryTracking order={order} preview={preview} />
    </article>
  )
}
