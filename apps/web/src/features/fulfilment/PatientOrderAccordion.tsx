import type { ReactNode } from 'react'
import type { Order, OrderSnapshot } from './api'
import { trackingOrder } from './api'
import { orderLabels, trackingTime } from './model'
import { orderAppearance } from './orderAppearance'
import { PatientAccordionItem } from '../patient/PatientAccordionItem'
import { canReviewMedicinePayment } from './patientMedicines'

export function PatientOrderAccordion({
  orders,
  selectedId,
  onSelect,
  snapshot,
  children,
}: {
  orders: Order[]
  selectedId: string | null
  onSelect: (id: string | null) => void
  snapshot?: OrderSnapshot
  children: ReactNode
}) {
  if (!orders.length)
    return <p role="status">No medication orders to display.</p>
  return (
    <ul className="divide-y">
      {orders.map((order) => {
        const current = trackingOrder(
          order,
          snapshot?.order.order_id === order.order_id
            ? snapshot.delivery
            : (order.delivery_snapshot ?? null),
        )
        const appearance = orderAppearance(current)
        const open = selectedId === order.order_id
        return (
          <li key={order.order_id}>
            <PatientAccordionItem
              title={
                <span className="flex flex-wrap items-center gap-2">
                  Medication order{' '}
                  <span className={`text-xs ${appearance.text}`}>
                    {appearance.label}
                  </span>
                </span>
              }
              summary={
                <>
                  <span className="block">
                    {trackingTime(order.created_at)}
                    {appearance.label !== orderLabels[order.status] &&
                      ` · ${orderLabels[order.status]}`}
                  </span>
                  <span className="block">
                    {order.items.map((item) => item.display_name).join(', ') ||
                      'Prescribed medicines'}
                  </span>
                </>
              }
              open={open}
              onToggle={() => onSelect(open ? null : order.order_id)}
            >
              {children}
            </PatientAccordionItem>
            {!open && canReviewMedicinePayment(order) && (
              <button
                type="button"
                className="mb-5 rounded-lg bg-teal-800 px-5 py-3 font-medium text-white"
                onClick={() => onSelect(order.order_id)}
              >
                Review medicines &amp; pay
              </button>
            )}
          </li>
        )
      })}
    </ul>
  )
}
