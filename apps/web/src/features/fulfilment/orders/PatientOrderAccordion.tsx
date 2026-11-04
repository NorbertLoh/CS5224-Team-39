import type { Order, OrderSnapshot } from '@/features/fulfilment/api'
import { trackingOrder } from '@/features/fulfilment/domain/tracking'
import { orderLabels, trackingTime } from '@/features/fulfilment/domain/model'
import { orderAppearance } from '@/features/fulfilment/domain/orderAppearance'
import { PatientAccordionItem } from '@/features/patient/components/PatientAccordionItem'
import { PatientStatusBadge } from '@/features/patient/components/PatientStatusBadge'
import type { ReactNode } from 'react'

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
    <ul className="space-y-3">
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
          <li
            key={order.order_id}
            className="rounded-2xl border border-slate-300 bg-white px-4 sm:px-5"
          >
            <PatientAccordionItem
              title={
                <span className="flex flex-wrap items-center gap-2">
                  Medication order{' '}
                  <PatientStatusBadge
                    label={appearance.label}
                    colour={appearance.badge}
                  />
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
          </li>
        )
      })}
    </ul>
  )
}
