import type { Order } from '@/features/fulfilment/api'
import { MedicationOrderAction } from '@/features/records/patient/MedicationOrderAction'
import type { Prescription } from '@/features/records/types'
import { consultationPrice } from '@/lib/money'
import type { ReactNode } from 'react'

export function PatientMedicationCard({
  prescription,
  order,
  checking,
  unavailable,
  priced = false,
  children,
}: {
  prescription: Prescription
  order?: Order
  checking: boolean
  unavailable: boolean
  priced?: boolean
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
      ) : !order && !priced ? (
        <p className="text-sm text-slate-600">
          The clinic is pricing your medicines. Payment will be available once pricing is complete.
        </p>
      ) : (
        <>
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
          <MedicationOrderAction prescription={prescription} order={order} />
        </>
      )}
    </div>
  )
}
