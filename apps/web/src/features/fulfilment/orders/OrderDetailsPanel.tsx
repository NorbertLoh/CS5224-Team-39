import type { OrderSnapshot } from '@/features/fulfilment/api'
import { trackingOrder } from '@/features/fulfilment/domain/tracking'
import type { OrderContext } from '@/features/fulfilment/domain/model'
import { ClinicOrderContact } from '@/features/fulfilment/orders/ClinicOrderContact'
import { PatientOrderDetails } from '@/features/fulfilment/orders/PatientOrderDetails'
import { OrderMedicationPricing } from '@/features/fulfilment/pricing/OrderMedicationPricing'
import { LiveMedicineReadiness } from '@/features/fulfilment/readiness/LiveMedicineReadiness'
import { TrackingOrderDetails } from '@/features/fulfilment/tracking/TrackingOrderDetails'

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
      contact={<ClinicOrderContact order={snapshot.order} />}
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
