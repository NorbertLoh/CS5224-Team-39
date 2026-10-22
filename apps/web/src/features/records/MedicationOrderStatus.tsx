import type { Order } from '../fulfilment/api'
import { medicineProgress } from '../fulfilment/patientMedicines'
import { consultationPrice } from '../../lib/money'

export function MedicationOrderStatus({ order }: { order?: Order }) {
  const progress = medicineProgress(order)
  const paid = order?.payment_status === 'succeeded'
  return (
    <>
      <p role="status" className="font-medium text-teal-900">
        {progress}
      </p>
      {order && (
        <p className="text-sm">
          {order.total ? 'Medicines + delivery: ' : 'Medicines: '}
          {consultationPrice(
            (order.total ?? order.medication_subtotal).amount_minor,
            'SGD',
          )}
          {!order.total && ' · Delivery calculated after entering your address'}
        </p>
      )}
      {paid && (
        <ol
          aria-label="Medication delivery progress"
          className="flex flex-wrap gap-3 text-sm"
        >
          <li>Payment confirmed</li>
          <li
            aria-current={
              progress === 'Preparing medicines' ? 'step' : undefined
            }
          >
            {order.medicine_status === 'ready'
              ? 'Medicines prepared'
              : 'Preparing medicines'}
          </li>
          {progress !== 'Preparing medicines' && (
            <li aria-current="step">{progress}</li>
          )}
        </ol>
      )}
    </>
  )
}
