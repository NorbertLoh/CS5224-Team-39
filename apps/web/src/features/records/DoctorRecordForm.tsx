import { useState } from 'react'
import { ConsultationNoteForm } from './ConsultationNoteForm'
import { PrescriptionEditor } from './PrescriptionEditor'
import { prescriptionFixture } from './fixtures'

export function DoctorRecordForm() {
  const [message, setMessage] = useState('')
  return (
    <section
      className="space-y-6 rounded-xl border bg-white p-6"
      aria-labelledby="record-heading"
    >
      <div>
        <h2 id="record-heading" className="text-xl font-semibold">
          Consultation notes and prescription
        </h2>
        <p className="mt-2 text-sm text-amber-800">
          Synthetic preview. Saves and issuance last only until you leave or
          reload this page. No clinical record is created.
        </p>
      </div>
      <dl className="grid gap-2 text-sm sm:grid-cols-2">
        <div>
          <dt className="font-medium">Appointment</dt>
          <dd className="break-all">{prescriptionFixture.appointment_id}</dd>
        </div>
        <div>
          <dt className="font-medium">Patient</dt>
          <dd className="break-all">{prescriptionFixture.patient_id}</dd>
        </div>
        <div>
          <dt className="font-medium">Clinic</dt>
          <dd className="break-all">{prescriptionFixture.tenant_id}</dd>
        </div>
        <div>
          <dt className="font-medium">Session</dt>
          <dd>In progress (fixture)</dd>
        </div>
      </dl>
      <ConsultationNoteForm onStatus={setMessage} />
      <PrescriptionEditor onStatus={setMessage} />
      <p role="status" aria-live="polite">
        {message}
      </p>
    </section>
  )
}
