import { deliveryLabels, trackingGuidance, trackingTime } from './model'
import type { TrackingOrder } from './model'

export function DeliveryTracking({
  order,
  preview = true,
}: {
  order: TrackingOrder
  preview?: boolean
}) {
  return (
    <section
      className="space-y-3 rounded-xl bg-slate-50 p-4"
      aria-labelledby="delivery-tracking-heading"
    >
      <h3 id="delivery-tracking-heading" className="font-semibold">
        Delivery tracking
      </h3>
      <div role="status" className="space-y-2">
        <p className="font-medium">
          {order.delivery
            ? deliveryLabels[order.delivery.status]
            : 'No delivery confirmed'}
        </p>
        <p className="text-sm">{trackingGuidance(order, preview)}</p>
      </div>
      {order.delivery && (
        <dl className="space-y-2 text-sm">
          <div>
            <dt className="font-medium">Delivery reference</dt>
            <dd className="break-all">{order.delivery.delivery_id}</dd>
          </div>
          <div>
            <dt className="font-medium">Delivery status updated</dt>
            <dd>{trackingTime(order.delivery.updated_at)}</dd>
          </div>
        </dl>
      )}
    </section>
  )
}
