import type { Order } from '@/features/fulfilment/api'
import { MedicationCorrectionEditor } from '@/features/fulfilment/pricing/MedicationCorrectionEditor'
import { consultationPrice } from '@/lib/money'

export function OrderMedicationPricing({
  order,
  token,
}: {
  order: Order
  token: string
}) {
  return (
    <section
      className="space-y-4 rounded-xl border bg-white p-5"
      aria-label="Medication pricing"
    >
      <h3 className="font-semibold">1. Medication pricing</h3>
      <MedicationCorrectionEditor
        tenantId={order.tenant_id}
        prescriptionId={order.prescription_id}
        token={token}
        disabled={
          order.status !== 'awaiting_payment' ||
          order.payment_status !== 'unpaid' ||
          Boolean(order.quote_id || order.payment_id || order.delivery_id) ||
          order.medicine_status !== 'not_ready'
        }
      />
      <p className="text-sm text-slate-600">
        Pricing is complete. These prices were saved when the patient opened
        this order and are locked.
      </p>
      <ul className="space-y-3">
        {order.items.map((item) => (
          <li
            key={item.prescription_item_id}
            className="space-y-2 rounded-lg border p-4 text-sm"
          >
            <h4 className="font-medium">{item.display_name}</h4>
            <dl className="grid grid-cols-2 gap-2">
              <dt className="text-slate-600">Quantity</dt>
              <dd>{item.quantity}</dd>
              <dt className="text-slate-600">Unit price</dt>
              <dd>{consultationPrice(item.unit_price.amount_minor, 'SGD')}</dd>
              <dt className="text-slate-600">Line total</dt>
              <dd>{consultationPrice(item.line_total.amount_minor, 'SGD')}</dd>
            </dl>
          </li>
        ))}
      </ul>
      <p className="text-sm font-medium">
        Medication total:{' '}
        {consultationPrice(order.medication_subtotal.amount_minor, 'SGD')}
      </p>
    </section>
  )
}
