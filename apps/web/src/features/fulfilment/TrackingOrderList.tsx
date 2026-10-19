import { orderLabels } from './model'
import type { TrackingOrder } from './model'

export function TrackingOrderList({
  orders,
  selectedId,
  onSelect,
}: {
  orders: TrackingOrder[]
  selectedId: string | null
  onSelect: (id: string) => void
}) {
  return (
    <section className="space-y-3" aria-labelledby="tracking-orders-heading">
      <h2 id="tracking-orders-heading" className="text-xl font-semibold">
        Orders
      </h2>
      {orders.length === 0 ? (
        <p role="status">No medication orders to display.</p>
      ) : (
        <ul className="space-y-3">
          {orders.map((order) => (
            <li key={order.order_id}>
              <button
                className="w-full space-y-2 rounded-xl border p-4 text-left aria-pressed:border-slate-900 aria-pressed:bg-slate-50"
                aria-pressed={selectedId === order.order_id}
                onClick={() => onSelect(order.order_id)}
              >
                <span className="block font-semibold">{order.label}</span>
                <span className="block text-sm">
                  {orderLabels[order.status]} ·{' '}
                  {order.medicine_status === 'ready'
                    ? 'Medicine ready'
                    : 'Medicine not ready'}
                </span>
                <span className="block break-all text-xs text-slate-600">
                  Order {order.order_id}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
