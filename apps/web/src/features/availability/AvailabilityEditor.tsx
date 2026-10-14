import { useState } from 'react'
import { Button } from '../../components/ui/button'
import { ErrorState } from '../../components/ErrorState'
import { addSlot, fixtureClinics, fixtureDoctors, formatSlotTime, initialSlots, removeSlot, singaporeDate, slotStart } from './fixtures'

const fieldClass = 'mt-2 w-full rounded-lg border bg-white px-3 py-2 text-base'

export function AvailabilityEditor() {
  const [slots, setSlots] = useState(initialSlots)
  const [tenantId, setTenantId] = useState(fixtureClinics[0].tenant_id)
  const [doctorId, setDoctorId] = useState(fixtureDoctors(tenantId)[0].subject_id)
  const [date, setDate] = useState(() => singaporeDate(Date.now() + 86400000))
  const [time, setTime] = useState('09:00')
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const start = slotStart(date, time)
  const endTime = Number.isFinite(start) ? formatSlotTime(new Date(start + 1800000).toISOString()) : '—'
  const visible = slots.filter(slot => slot.tenant_id === tenantId && slot.doctor_id === doctorId && singaporeDate(Date.parse(slot.starts_at)) === date)
    .sort((a, b) => a.starts_at.localeCompare(b.starts_at))
  function clearFeedback() { setError(''); setMessage('') }

  return <section className="mt-8 space-y-6" aria-labelledby="availability-heading">
    <div>
      <h2 id="availability-heading" className="text-2xl font-semibold">Your availability</h2>
      <p className="mt-2 text-slate-600">Set your consultation times. Each slot lasts 30 minutes.</p>
    </div>
    <aside className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-950">
      <strong>Fixture preview</strong><p className="mt-1">Choose a demo clinic and doctor to try the editor. Changes last until you reload this page and do not change real availability.</p>
    </aside>
    <div className="grid gap-4 sm:grid-cols-2">
      <label className="text-sm font-medium">Demo clinic<select className={fieldClass} value={tenantId} onChange={event => {
        const next = event.target.value
        setTenantId(next); setDoctorId(fixtureDoctors(next)[0].subject_id); clearFeedback()
      }}>{fixtureClinics.map(clinic => <option key={clinic.tenant_id} value={clinic.tenant_id}>{clinic.name}</option>)}</select></label>
      <label className="text-sm font-medium">Demo doctor<select className={fieldClass} value={doctorId} onChange={event => { setDoctorId(event.target.value); clearFeedback() }}>
        {fixtureDoctors(tenantId).map(doctor => <option key={doctor.subject_id} value={doctor.subject_id}>{doctor.display_name}</option>)}
      </select></label>
    </div>
    <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,2fr)]">
      <form className="space-y-4 rounded-xl border p-5" onSubmit={event => {
        event.preventDefault(); clearFeedback()
        try { setSlots(addSlot(slots, tenantId, doctorId, date, time)); setMessage('30-minute slot added to the fixture schedule.') }
        catch (cause) { setError((cause as Error).message) }
      }}>
        <h3 className="text-lg font-semibold">Add a slot</h3>
        <p className="text-sm text-slate-600">All dates and times are in Singapore time (SGT, UTC+8).</p>
        <label className="block text-sm font-medium">Date<input className={fieldClass} type="date" required value={date} onChange={event => { setDate(event.target.value); clearFeedback() }} /></label>
        <label className="block text-sm font-medium">Start time<input className={fieldClass} type="time" required value={time} onChange={event => { setTime(event.target.value); clearFeedback() }} /></label>
        <p className="text-sm text-slate-600">End time: {endTime} SGT (30 minutes later)</p>
        <Button type="submit" size="lg">Add slot</Button>
      </form>
      <div className="space-y-4 rounded-xl border p-5">
        <h3 className="text-lg font-semibold">Slots for {date || 'selected date'}</h3>
        <p className="text-sm text-slate-600">{visible.length} slots · SGT. Unavailable or past slots cannot be removed.</p>
        {visible.length === 0 && <p className="rounded-lg bg-slate-50 p-6 text-slate-600">No slots on this date. Choose another date or add your first slot.</p>}
        <ul className="divide-y">{visible.map(slot => <li key={slot.slot_id} className="flex flex-wrap items-center justify-between gap-3 py-4">
          <div><p className="font-medium"><time dateTime={slot.starts_at}>{formatSlotTime(slot.starts_at)}</time> – <time dateTime={slot.ends_at}>{formatSlotTime(slot.ends_at)}</time></p>
            <p className="text-sm text-slate-600">{slot.availability === 'available' ? 'Available' : 'Unavailable'}</p></div>
          <Button type="button" variant="outline" disabled={slot.availability !== 'available' || Date.parse(slot.starts_at) <= Date.now()}
            aria-label={`Remove ${formatSlotTime(slot.starts_at)} slot`} onClick={() => {
              clearFeedback()
              try { setSlots(removeSlot(slots, slot.slot_id, tenantId, doctorId)); setMessage('Slot removed from the fixture schedule.') }
              catch (cause) { setError((cause as Error).message) }
            }}>Remove</Button>
        </li>)}</ul>
      </div>
    </div>
    {error && <ErrorState message={error} />}
    <p role="status" aria-live="polite" className="text-sm text-emerald-800">{message}</p>
  </section>
}
