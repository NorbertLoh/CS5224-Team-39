import type { Order } from '@/features/fulfilment/api'
import { orderLabels, trackingTime } from '@/features/fulfilment/domain/model'
import { orderAppearance } from '@/features/fulfilment/domain/orderAppearance'
import { trackingOrder } from '@/features/fulfilment/domain/tracking'
import { PatientAccordionItem } from '@/features/patient/components/PatientAccordionItem'
import type { ReactNode } from 'react'

export function ClinicDeliveryOrders({
  orders,
  selectedId,
  onSelect,
  orderDetails,
}: {
  orders: Order[]
  selectedId: string | null
  onSelect: (id: string | null) => void
  orderDetails: ReactNode
}) {
  return (
    <div className="space-y-4">
      {!orders.length && (
        <p className="text-sm text-slate-600">
          Medicine orders will appear here.
        </p>
      )}
      {orders.map((order) => {
        const appearance = orderAppearance(trackingOrder(order))
        return (
          <div
            key={order.order_id}
            className={`rounded-2xl border-2 bg-white px-5 ${appearance.border}`}
          >
            <PatientAccordionItem
              title={
                <span className="flex flex-wrap items-center gap-2">
                  <span>Order {order.order_id.slice(-8)}</span>
                  <span className={`text-xs ${appearance.text}`}>
                    {appearance.label}
                  </span>
                </span>
              }
              summary={
                <>
                  <span className="block">
                    {order.items.map((item) => item.display_name).join(', ')}
                  </span>
                  <span className="block">
                    {trackingTime(order.created_at)} ·{' '}
                    {orderLabels[order.status]} ·{' '}
                    {order.medicine_status === 'ready'
                      ? 'Medicine ready'
                      : 'Medicine not ready'}
                  </span>
                </>
              }
              open={selectedId === order.order_id}
              onToggle={() =>
                onSelect(selectedId === order.order_id ? null : order.order_id)
              }
            >
              {selectedId === order.order_id && orderDetails}
            </PatientAccordionItem>
          </div>
        )
      })}
    </div>
  )
}
