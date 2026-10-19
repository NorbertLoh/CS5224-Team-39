import { money, order, prescription } from './model'
import type { OrderState } from './model'

export function OrderSummary({ state }: { state: OrderState }) {
  return (
    <section
      className="space-y-4 rounded-xl border p-5"
      aria-labelledby="order-heading"
    >
      <div>
        <p className="text-sm text-slate-600">
          Demo clinic · Issued prescription
        </p>
        <h2 id="order-heading" className="text-xl font-semibold">
          Medication order
        </h2>
      </div>
      <dl className="space-y-2 text-sm">
        <div>
          <dt className="font-medium">Prescription reference</dt>
          <dd className="break-all">{prescription.prescription_id}</dd>
        </div>
        {state.created && (
          <div>
            <dt className="font-medium">Order reference</dt>
            <dd className="break-all">{order.order_id}</dd>
          </div>
        )}
      </dl>
      <ul className="space-y-3">
        {order.items.map((item) => (
          <li
            key={item.prescription_item_id}
            className="rounded-lg bg-slate-50 p-4"
          >
            <h3 className="font-medium">{item.display_name}</h3>
            <p className="mt-1 text-sm">
              {item.quantity} dispensing units ×{' '}
              {money(item.unit_price.amount_minor)}
            </p>
            <p className="mt-2 font-semibold">
              {money(item.line_total.amount_minor)}
            </p>
          </li>
        ))}
      </ul>
      <p className="text-sm text-slate-600">
        Quantities follow the issued prescription. Prices use the synthetic
        fulfilment snapshot.
      </p>
      <dl className="space-y-3 border-t pt-4">
        <div className="flex justify-between gap-4">
          <dt>Medication subtotal</dt>
          <dd>
            {money(
              state.quote?.medicationSubtotal ??
                order.medication_subtotal.amount_minor,
            )}
          </dd>
        </div>
        <div className="flex justify-between gap-4">
          <dt>Delivery fee</dt>
          <dd>
            {state.quote ? money(state.quote.deliveryFee) : 'Request a quote'}
          </dd>
        </div>
        <div className="flex justify-between gap-4 text-lg font-semibold">
          <dt>Total (SGD)</dt>
          <dd>{state.quote ? money(state.quote.total) : 'Awaiting quote'}</dd>
        </div>
      </dl>
    </section>
  )
}
