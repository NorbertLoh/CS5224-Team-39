import type { OrderSnapshot } from './api'
import { trackingOrder } from './api'
import type { PreviewContext } from './model'
import { LiveMedicationCheckout } from './LiveMedicationCheckout'
import { TrackingOrderDetails } from './TrackingOrderDetails'
import { LiveMedicineReadiness } from './LiveMedicineReadiness'

export function OrderDetailsPanel({
  snapshot,
  context,
  refresh,
}: {
  snapshot: OrderSnapshot
  context: PreviewContext
  refresh: () => Promise<OrderSnapshot>
}) {
  const patient = context.role === 'patient'
  return (
    <>
      {patient && (
        <LiveMedicationCheckout
          key={snapshot.order.order_id}
          snapshot={snapshot}
          subject={context.patientId}
          refresh={refresh}
        />
      )}
      <TrackingOrderDetails
        key={snapshot.order.order_id}
        order={trackingOrder(snapshot.order, snapshot.delivery)}
        context={context}
        onReady={() => undefined}
        preview={false}
        readiness={
          patient ? (
            <></>
          ) : (
            <LiveMedicineReadiness
              order={snapshot.order}
              context={context}
              onRefresh={() => {
                void refresh().catch(() => undefined)
              }}
            />
          )
        }
      />
    </>
  )
}
