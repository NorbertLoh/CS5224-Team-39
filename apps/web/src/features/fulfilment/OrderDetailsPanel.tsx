import type { OrderSnapshot } from './api'
import { trackingOrder } from './api'
import type { OrderContext } from './model'
import { PatientOrderDetails } from './PatientOrderDetails'
import { TrackingOrderDetails } from './TrackingOrderDetails'
import { LiveMedicineReadiness } from './LiveMedicineReadiness'
import { OrderMedicationPricing } from './OrderMedicationPricing'

export function OrderDetailsPanel({
  snapshot,
  context,
  refresh,
  token,
}: {
  snapshot: OrderSnapshot
  context: OrderContext
  refresh: () => Promise<OrderSnapshot>
  token: string
}) {
  if (context.role === 'patient')
    return (
      <PatientOrderDetails
        snapshot={snapshot}
        subject={context.patientId}
        refresh={refresh}
      />
    )
  return (
    <TrackingOrderDetails
      key={snapshot.order.order_id}
      order={trackingOrder(snapshot.order, snapshot.delivery)}
      pricing={<OrderMedicationPricing order={snapshot.order} token={token} />}
      readiness={
        <LiveMedicineReadiness
          order={snapshot.order}
          context={context}
          onRefresh={() => {
            void refresh().catch(() => undefined)
          }}
        />
      }
    />
  )
}
