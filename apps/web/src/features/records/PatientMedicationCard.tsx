import type { ReactNode } from 'react'
import type { Prescription } from './types'
import type { Order } from '../fulfilment/api'
import { OpenMedicationOrderButton } from '../fulfilment/OpenMedicationOrderButton'
import {
  canReviewMedicinePayment,
  medicineProgress,
} from '../fulfilment/patientMedicines'
import { consultationPrice } from '../../lib/money'

export function PatientMedicationCard({
  prescription,
  order,
  checking,
  unavailable,
  children,
}: {
  prescription: Prescription
  order?: Order
  checking: boolean
  unavailable: boolean
  children: ReactNode
}) {
  if (prescription.status !== 'issued' || prescription.items.length === 0)
    return children
  const review = canReviewMedicinePayment(order)
  const progress = medicineProgress(order)
  const paid = order?.payment_status === 'succeeded'
  return (
    <article className="space-y-4 rounded-xl border border-teal-200 bg-teal-50 p-5">
      <div>
        <h3 className="text-xl font-semibold">
          {checking || unavailable
            ? 'Your prescribed medicines'
            : review
              ? 'Your prescribed medicines are ready to order'
              : progress}
        </h3>
        <p className="mt-1 text-sm text-slate-600">
          Medication and delivery are paid separately from your consultation.
        </p>
      </div>
      {children}
      <ul className="space-y-2">
        {prescription.items.map((item) => (
          <li
            key={item.prescription_item_id}
            className="flex flex-wrap justify-between gap-2 text-sm"
          >
            <span className="font-medium">{item.display_name}</span>
            <span>Quantity: {item.quantity}</span>
          </li>
        ))}
      </ul>
      {checking ? (
        <p role="status">Checking your medication order...</p>
      ) : unavailable ? (
        <p role="alert">
          Could not check your medication order. Refresh to try again.
        </p>
      ) : (
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
              {!order.total &&
                ' · Delivery calculated after entering your address'}
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
      )}
    </article>
  )
}
