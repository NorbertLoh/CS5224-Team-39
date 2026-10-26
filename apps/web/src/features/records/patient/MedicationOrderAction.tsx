import type { Order } from '@/features/fulfilment/api'
import { canReviewMedicinePayment } from '@/features/fulfilment/domain/patientMedicines'
import { OpenMedicationOrderButton } from '@/features/fulfilment/orders/OpenMedicationOrderButton'
import type { Prescription } from '@/features/records/types'

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
