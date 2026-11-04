import type { TrackingOrder } from '@/features/fulfilment/domain/model'
import {
  deliveryLabels,
  trackingGuidance,
  trackingTime,
} from '@/features/fulfilment/domain/model'

const deliverySteps = [
  { status: 'submitted', label: 'Courier assigned' },
  { status: 'picked_up', label: 'Out for delivery' },
  { status: 'delivered', label: 'Delivered' },
] as const

function PatientDeliveryProgress({ order }: { order: TrackingOrder }) {
  const status = order.delivery?.status
  const current = deliverySteps.findIndex((step) => step.status === status)
  const hasIssue =
    status === 'cancelled' || status === 'failed' || status === 'unknown'

  return (
    <div role="status" className="space-y-2">
      <ol aria-label="Delivery progress" className="grid grid-cols-3 gap-2">
        {deliverySteps.map((step, index) => (
          <li
            key={step.status}
            aria-current={index === current ? 'step' : undefined}
            className="space-y-1.5"
          >
            <span
              aria-hidden="true"
              className={`block h-2 rounded-full ${
                index > current
                  ? 'bg-slate-200'
                  : status === 'delivered'
                    ? 'bg-emerald-600'
                    : 'bg-teal-600'
              }`}
            />
            <span
              className={`block text-xs ${
                index === current ? 'font-semibold text-slate-900' : 'text-slate-600'
              }`}
            >
              {step.label}
            </span>
          </li>
        ))}
      </ol>
      {current === -1 && (
        <>
          <p className={`text-sm font-medium ${hasIssue ? 'text-red-700' : 'text-slate-700'}`}>
            {status ? deliveryLabels[status] : 'No delivery confirmed'}
          </p>
          <p className="text-sm text-slate-600">{trackingGuidance(order)}</p>
        </>
      )}
    </div>
  )
}

export function DeliveryTracking({
  order,
  compact = false,
}: {
  order: TrackingOrder
  compact?: boolean
}) {
  return (
    <section
      className={
        compact
          ? 'space-y-2 border-t pt-4'
          : 'space-y-3 rounded-xl bg-slate-50 p-4'
      }
      aria-labelledby="delivery-tracking-heading"
    >
      <h3 id="delivery-tracking-heading" className="font-semibold">
        Delivery tracking
      </h3>
      {compact ? (
        <PatientDeliveryProgress order={order} />
      ) : (
        <div role="status" className="space-y-2">
          <p className="font-medium">
            {order.delivery
              ? deliveryLabels[order.delivery.status]
              : 'No delivery confirmed'}
          </p>
          <p className="text-sm">{trackingGuidance(order)}</p>
        </div>
      )}
      {!compact && order.delivery && (
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
