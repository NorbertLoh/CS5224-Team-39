import type { ReactNode } from 'react'
import type { Prescription } from './types'
import type { Order } from '../fulfilment/api'
import {
  canReviewMedicinePayment,
  medicineProgress,
} from '../fulfilment/patientMedicines'
import { MedicationOrderStatus } from './MedicationOrderStatus'
import { MedicationOrderAction } from './MedicationOrderAction'

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
  return (
    <div className="space-y-4">
      <div>
        <h3 className="font-semibold">
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
      {checking ? (
        <p role="status">Checking your medication order...</p>
      ) : unavailable ? (
        <p role="alert">
          Could not check your medication order. Refresh to try again.
        </p>
      ) : (
        <>
          <MedicationOrderStatus order={order} />
          <MedicationOrderAction prescription={prescription} order={order} />
        </>
      )}
    </div>
  )
}
