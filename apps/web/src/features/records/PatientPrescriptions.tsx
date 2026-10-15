import { useState } from 'react'
import { prescriptionFixture } from './fixtures'
import type { Prescription } from './fixtures'
import { PrescriptionDetails } from './PrescriptionDetails'
import { PrescriptionSummary } from './PrescriptionSummary'

export function PatientPrescriptions() {
  const [preview, setPreview] = useState('available')
  const [selected, setSelected] = useState(false)
  const prescription: Prescription = {
    ...prescriptionFixture,
    status: 'issued',
  }
  return (
    <section
      className="mt-8 space-y-4 rounded-xl border p-6"
      aria-labelledby="prescription-heading"
    >
      <h2 id="prescription-heading" className="text-xl font-semibold">
        Prescriptions
      </h2>
      <p className="text-sm text-amber-800">
        Synthetic preview. These placeholder records are independent of your
        account and are not treatment advice. No clinical API is connected.
      </p>
      <label className="flex max-w-sm flex-col gap-2 text-sm">
        Preview scenario
        <select
          className="rounded border px-3 py-2"
          value={preview}
          onChange={(event) => {
            setPreview(event.target.value)
            setSelected(false)
          }}
        >
          <option value="available">Prescription available</option>
          <option value="empty">No prescriptions</option>
          <option value="unavailable">Prescription unavailable</option>
        </select>
      </label>
      {preview === 'empty' && (
        <p role="status">No prescriptions for this appointment.</p>
      )}
      {preview === 'unavailable' && (
        <p role="status">
          Prescription unavailable. Return to your appointments or try again
          later.
        </p>
      )}
      {preview === 'available' && (
        <>
          <PrescriptionSummary
            prescription={prescription}
            selected={selected}
            onToggle={() => setSelected((current) => !current)}
          />
          {selected && <PrescriptionDetails prescription={prescription} />}
        </>
      )}
    </section>
  )
}
