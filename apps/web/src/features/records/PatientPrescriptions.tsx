import { useState } from 'react'
import { prescriptionFixture } from './fixtures'
import type { Prescription } from './fixtures'

export function PrescriptionDetails({ prescription }: { prescription: Prescription }) {
  return <article className="space-y-4 rounded border p-4">
    <h3 className="font-semibold">Prescription details</h3>
    <dl className="space-y-2 text-sm">
      <div><dt className="font-medium">Prescription</dt><dd className="break-all">{prescription.prescription_id}</dd></div>
      <div><dt className="font-medium">Appointment</dt><dd className="break-all">{prescription.appointment_id}</dd></div>
      <div><dt className="font-medium">Status</dt><dd>{prescription.status}</dd></div>
      <div><dt className="font-medium">Issued (Singapore time)</dt><dd>{prescription.issued_at ? new Intl.DateTimeFormat('en-SG', { timeZone: 'Asia/Singapore', dateStyle: 'medium', timeStyle: 'short' }).format(new Date(prescription.issued_at)) : 'Not issued'}</dd></div>
    </dl>
    <ul className="space-y-3">{prescription.items.map(item => <li key={item.prescription_item_id} className="rounded bg-slate-50 p-3">
      <h4 className="font-medium">{item.display_name}</h4>
      <p className="text-sm">Quantity: {item.quantity} dispensing units</p>
      <p className="mt-2 whitespace-pre-wrap text-sm">{item.instructions}</p>
    </li>)}</ul>
    {prescription.status !== 'issued' && <p className="text-sm">This prescription is {prescription.status} and cannot be used to create an order.</p>}
    <p className="text-sm text-slate-600">PDF downloads and medication orders will be available after their services are connected.</p>
  </article>
}

export function PatientPrescriptions() {
  const [preview, setPreview] = useState('available')
  const [selected, setSelected] = useState(false)
  const prescription: Prescription = { ...prescriptionFixture, status: 'issued' }
  return <section className="mt-8 space-y-4 rounded-xl border p-6" aria-labelledby="prescription-heading">
    <h2 id="prescription-heading" className="text-xl font-semibold">Prescriptions</h2>
    <p className="text-sm text-amber-800">Synthetic preview. These placeholder records are independent of your account and are not treatment advice. No clinical API is connected.</p>
    <label className="flex max-w-sm flex-col gap-2 text-sm">Preview scenario<select className="rounded border px-3 py-2" value={preview} onChange={event => { setPreview(event.target.value); setSelected(false) }}>
      <option value="available">Prescription available</option><option value="empty">No prescriptions</option><option value="unavailable">Prescription unavailable</option>
    </select></label>
    {preview === 'empty' && <p role="status">No prescriptions for this appointment.</p>}
    {preview === 'unavailable' && <p role="status">Prescription unavailable. Return to your appointments or try again later.</p>}
    {preview === 'available' && <>
      <ul><li><button type="button" className="w-full rounded border p-4 text-left" onClick={() => setSelected(current => !current)} aria-expanded={selected}>
        <span className="block font-medium">Issued prescription · Demo clinic</span>
        <span className="block text-sm">12 Oct 2026 · {prescription.items.length} medication · {selected ? 'Hide details' : 'View details'}</span>
      </button></li></ul>
      {selected && <PrescriptionDetails prescription={prescription} />}
    </>}
  </section>
}
