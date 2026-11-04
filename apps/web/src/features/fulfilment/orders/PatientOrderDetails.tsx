import type { OrderSnapshot } from '@/features/fulfilment/api'
import { trackingOrder } from '@/features/fulfilment/domain/tracking'
import { LiveMedicationCheckout } from '@/features/fulfilment/checkout/LiveMedicationCheckout'
import { paymentLabels, trackingTime } from '@/features/fulfilment/domain/model'
import { DeliveryTracking } from '@/features/fulfilment/tracking/DeliveryTracking'

export function PatientOrderDetails({
  snapshot,
  subject,
  refresh,
}: {
  snapshot: OrderSnapshot
  subject: string
  refresh: () => Promise<OrderSnapshot>
}) {
  const { order, delivery } = snapshot
  return (
    <section
      aria-labelledby="patient-order-details-heading"
      className="space-y-4"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 id="patient-order-details-heading" className="font-semibold">
          Order details
        </h3>
        <p className="text-sm text-slate-600">
          {paymentLabels[order.payment_status]} ·{' '}
          {order.medicine_status === 'ready'
            ? 'Medicines ready'
            : 'Medicines not ready'}
        </p>
      </div>
      <LiveMedicationCheckout
        snapshot={snapshot}
        subject={subject}
        refresh={refresh}
        compact
      />
      <DeliveryTracking order={trackingOrder(order, delivery)} compact />
      <details className="text-sm text-slate-600">
        <summary className="cursor-pointer">Order information</summary>
        <dl className="space-y-2 pt-3">
          <div>
            <dt className="font-medium">Order reference</dt>
            <dd className="break-all">{order.order_id}</dd>
          </div>
          <div>
            <dt className="font-medium">Prescription reference</dt>
            <dd className="break-all">{order.prescription_id}</dd>
          </div>
          {order.payment_id && (
            <div>
              <dt className="font-medium">Payment reference</dt>
              <dd className="break-all">{order.payment_id}</dd>
            </div>
          )}
          {delivery && (
            <div>
              <dt className="font-medium">Delivery reference</dt>
              <dd className="break-all">{delivery.delivery_id}</dd>
            </div>
          )}
          <div>
            <dt className="font-medium">Last updated</dt>
            <dd>{trackingTime(order.updated_at)}</dd>
          </div>
        </dl>
      </details>
    </section>
  )
}
