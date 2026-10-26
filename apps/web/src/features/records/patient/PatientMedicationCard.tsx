import type { Order } from '@/features/fulfilment/api'
import { MedicationOrderAction } from '@/features/records/patient/MedicationOrderAction'
import { MedicationOrderStatus } from '@/features/records/patient/MedicationOrderStatus'
import type { Prescription } from '@/features/records/types'
import type { ReactNode } from 'react'

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
  return (
    <div className="space-y-4">
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
