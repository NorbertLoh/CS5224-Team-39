import type { Prescription } from './types'
import { OpenMedicationOrderButton } from '../fulfilment/OpenMedicationOrderButton'

export function PrescriptionDetails({
  prescription,
  allowOrdering = false,
  compact = false,
}: {
  prescription: Prescription
  allowOrdering?: boolean
  compact?: boolean
}) {
  const information = (
    <dl className="space-y-2 text-sm">
      <div>
        <dt className="font-medium">Prescription</dt>
        <dd className="break-all">{prescription.prescription_id}</dd>
      </div>
      <div>
        <dt className="font-medium">Appointment</dt>
        <dd className="break-all">{prescription.appointment_id}</dd>
      </div>
      <div>
        <dt className="font-medium">Status</dt>
        <dd>{prescription.status}</dd>
      </div>
      <div>
        <dt className="font-medium">Issued (Singapore time)</dt>
        <dd>
          {prescription.issued_at
            ? new Intl.DateTimeFormat('en-SG', {
                timeZone: 'Asia/Singapore',
                dateStyle: 'medium',
                timeStyle: 'short',
              }).format(new Date(prescription.issued_at))
            : 'Not issued'}
        </dd>
      </div>
    </dl>
  )
  return (
    <article className={compact ? 'space-y-3' : 'space-y-4 rounded border p-4'}>
      <h3 className="font-semibold">
        {compact ? 'Medicines' : 'Prescription details'}
      </h3>
      {!compact && information}
      <ul className="space-y-3">
        {prescription.items.map((item) => (
          <li
            key={item.prescription_item_id}
            className="rounded bg-slate-50 p-3"
          >
            <h4 className="font-medium">{item.display_name}</h4>
            <p className="text-sm">
              Quantity: {item.quantity} dispensing units
            </p>
            <p className="mt-2 whitespace-pre-wrap text-sm">
              {item.instructions}
            </p>
          </li>
        ))}
      </ul>
      {compact && (
        <details className="text-sm text-slate-600">
          <summary className="cursor-pointer">Prescription information</summary>
          <div className="pt-3">{information}</div>
        </details>
      )}
      {prescription.status !== 'issued' && (
        <p className="text-sm">
          This prescription is {prescription.status} and cannot be used to
          create an order.
        </p>
      )}
      {allowOrdering && prescription.status === 'issued' && (
        <OpenMedicationOrderButton
          prescriptionId={prescription.prescription_id}
          subject={prescription.patient_id}
        />
      )}
    </article>
  )
}
