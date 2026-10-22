import type { Prescription } from './types'
import type { Order } from '../fulfilment/api'
import { canReviewMedicinePayment } from '../fulfilment/patientMedicines'
import { OpenMedicationOrderButton } from '../fulfilment/OpenMedicationOrderButton'

export function MedicationOrderAction({
  prescription,
  order,
}: {
  prescription: Prescription
  order?: Order
}) {
  const review = canReviewMedicinePayment(order)
  const paid = order?.payment_status === 'succeeded'
  return (
    <>
      {review ? (
        <>
          <OpenMedicationOrderButton
            prescriptionId={prescription.prescription_id}
            subject={prescription.patient_id}
          />
          <p className="text-sm text-slate-600">
            Confirm your delivery address and review the full total before
            paying.
          </p>
        </>
      ) : (
        order && (
          <a
            className="inline-block rounded-lg bg-teal-800 px-5 py-3 font-medium text-white"
            href={`/patient/medication-orders?order_id=${encodeURIComponent(order.order_id)}`}
          >
            {order.payment_status === 'pending'
              ? 'Check payment status'
              : paid
                ? 'View delivery details'
                : 'View medication order'}
          </a>
        )
      )}
    </>
  )
}
