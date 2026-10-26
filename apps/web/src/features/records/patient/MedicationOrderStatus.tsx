import type { Order } from '@/features/fulfilment/api'
import { medicineProgress } from '@/features/fulfilment/domain/patientMedicines'
import { consultationPrice } from '@/lib/money'

export function MedicationOrderStatus({ order }: { order?: Order }) {
  const progress = medicineProgress(order)
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
    </>
  )
}
