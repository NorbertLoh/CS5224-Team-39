import { DeliveryTracking } from './DeliveryTracking'
import { orderLabels, paymentLabels, trackingTime } from './model'
import type { TrackingOrder } from './model'
import { consultationPrice } from '../../lib/money'
import type { ReactNode } from 'react'

export function TrackingOrderDetails({
  order,
  readiness,
  pricing,
}: {
  order: TrackingOrder
  readiness: ReactNode
  pricing: ReactNode
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
      {pricing}
      {readiness}
      <DeliveryTracking order={order} />
    </article>
  )
}
