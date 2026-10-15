import { useState } from 'react'
import { catalogue, draftPrescription, prescriptionFixture, validItems } from './fixtures'
import type { Prescription, PrescriptionInput } from './fixtures'

const field = 'rounded border px-3 py-2'
const button = 'rounded border px-4 py-2 disabled:opacity-50'

export function DoctorRecordForm() {
  const [text, setText] = useState('')
  const [savedText, setSavedText] = useState('')
  const [items, setItems] = useState<PrescriptionInput[]>([])
  const [saved, setSaved] = useState<Prescription | null>(null)
  const [message, setMessage] = useState('')
  const issued = saved?.status === 'issued'
  const dirty = JSON.stringify(items) !== JSON.stringify(saved?.items.map(({ medication_id, quantity, instructions }) => ({ medication_id, quantity, instructions })) ?? [])
  const updateItem = (index: number, change: Partial<PrescriptionInput>) => {
    setItems(current => current.map((item, i) => i === index ? { ...item, ...change } : item))
    setMessage('')
  }
  return <section className="space-y-6 rounded-xl border bg-white p-6" aria-labelledby="record-heading">
    <div><h2 id="record-heading" className="text-xl font-semibold">Consultation notes and prescription</h2>
      <p className="mt-2 text-sm text-amber-800">Synthetic preview. Saves and issuance last only until you leave or reload this page. No clinical record is created.</p></div>
    <dl className="grid gap-2 text-sm sm:grid-cols-2">
      <div><dt className="font-medium">Appointment</dt><dd className="break-all">{prescriptionFixture.appointment_id}</dd></div>
      <div><dt className="font-medium">Patient</dt><dd className="break-all">{prescriptionFixture.patient_id}</dd></div>
      <div><dt className="font-medium">Clinic</dt><dd className="break-all">{prescriptionFixture.tenant_id}</dd></div>
      <div><dt className="font-medium">Session</dt><dd>In progress (fixture)</dd></div>
    </dl>
    <form className="space-y-3" onSubmit={event => { event.preventDefault(); setSavedText(text.trim()); setMessage('Note saved in this preview.') }}>
      <label className="flex flex-col gap-2">Consultation note<textarea className={field} value={text} onChange={event => setText(event.target.value)} required rows={5} /></label>
      <button className={button} disabled={!text.trim() || text.trim() === savedText}>Save preview note</button>
      {text.trim() !== savedText && <p className="text-sm text-slate-600">Note has unsaved changes.</p>}
    </form>
    <form className="space-y-4" onSubmit={event => { event.preventDefault(); setSaved(draftPrescription(items)); setMessage('Prescription draft saved in this preview.') }}>
      <div className="flex flex-wrap items-center justify-between gap-3"><h3 className="font-semibold">Prescription · {saved?.status ?? 'new'}</h3>
        {!issued && <button className={button} type="button" disabled={items.length >= catalogue.length} onClick={() => setItems(current => [...current, { medication_id: catalogue[0].medication_id, quantity: 1, instructions: '' }])}>Add medication</button>}</div>
      {!items.length && <p className="text-sm text-slate-600">No medications added. Select from the synthetic clinic catalogue to start.</p>}
      {items.map((item, index) => <fieldset key={index} className="space-y-3 rounded border p-4" disabled={issued}>
        <legend className="px-1">Medication {index + 1}</legend>
        <label className="flex flex-col gap-2">Catalogue item<select className={field} value={item.medication_id} onChange={event => updateItem(index, { medication_id: event.target.value })}>{catalogue.map(medication => <option key={medication.medication_id} value={medication.medication_id}>{medication.display_name}</option>)}</select></label>
        <label className="flex flex-col gap-2">Quantity (dispensing units)<input className={field} type="number" min="1" step="1" required value={Number.isNaN(item.quantity) ? '' : item.quantity} onChange={event => updateItem(index, { quantity: event.target.valueAsNumber })} /></label>
        <label className="flex flex-col gap-2">Instructions<textarea className={field} value={item.instructions} required onChange={event => updateItem(index, { instructions: event.target.value })} /></label>
        {!issued && <button type="button" className={button} onClick={() => setItems(current => current.filter((_, i) => i !== index))}>Remove medication {index + 1}</button>}
      </fieldset>)}
      {!issued && <div className="flex flex-wrap gap-3">
        <button className={button} disabled={!validItems(items) || !dirty}>Save preview draft</button>
        <button className={button} type="button" disabled={!saved || dirty || !validItems(items)} onClick={() => { setSaved(current => current && { ...current, status: 'issued', issued_at: new Date().toISOString(), updated_at: new Date().toISOString() }); setMessage('Prescription issued in this preview. Its content is now locked.') }}>Issue preview prescription</button>
      </div>}
      {issued && <p className="text-sm">Issued prescription content is locked. Reload to reset the synthetic preview.</p>}
    </form>
    <p role="status" aria-live="polite">{message}</p>
  </section>
}
