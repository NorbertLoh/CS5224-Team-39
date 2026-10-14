import { useState } from 'react'
import { Button } from '../../components/ui/button'
import { ErrorState } from '../../components/ErrorState'
import { fixtureClinics, fixtureDoctors, initialSlots, singaporeDate } from './fixtures'
import { applySelection, cellsInSelections, shiftDate, updateSelections, weekStart } from './timetable'
import type { Selection } from './timetable'
import { WeeklyTimetable } from './WeeklyTimetable'

const fieldClass = 'mt-2 w-full rounded-lg border bg-white px-3 py-2 text-base'

export function AvailabilityEditor() {
  const [slots, setSlots] = useState(initialSlots)
  const [tenantId, setTenantId] = useState(fixtureClinics[0].tenant_id)
  const [doctorId, setDoctorId] = useState(fixtureDoctors(tenantId)[0].subject_id)
  const [week, setWeek] = useState(() => weekStart(singaporeDate()))
  const [selections, setSelections] = useState<Selection[]>([])
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const dates = Array.from({ length: 7 }, (_, index) => shiftDate(week, index))
  const selected = cellsInSelections(selections, dates)
  function clearFeedback() { setSelections([]); setError(''); setMessage('') }
  function changeWeek(next: string) { setWeek(next); clearFeedback() }
  function apply(action: 'add' | 'remove') {
    if (!selections.length) return
    setError(''); setMessage('')
    try {
      setSlots(applySelection(slots, tenantId, doctorId, selections, dates, action))
      setMessage(action === 'add' ? `${selected.length} slots added to the fixture schedule.` : 'Selected availability removed from the fixture schedule.')
      setSelections([])
    } catch (cause) { setError((cause as Error).message) }
  }

  return <section className="mt-8 space-y-5" aria-labelledby="availability-heading">
    <div>
      <h2 id="availability-heading" className="text-2xl font-semibold">Your availability</h2>
      <p className="mt-2 text-slate-600">Drag across the timetable to select consultation times, then add or remove availability.</p>
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
    <div className="flex flex-wrap items-center justify-between gap-3">
      <div><h3 className="text-lg font-semibold">{week} – {dates[6]}</h3><p className="text-sm text-slate-600">Singapore time (SGT, UTC+8) · 30-minute slots</p></div>
      <div className="flex gap-2"><Button variant="outline" onClick={() => changeWeek(shiftDate(week, -7))} aria-label="Previous week">←</Button>
        <Button variant="outline" onClick={() => changeWeek(weekStart(singaporeDate()))}>This week</Button>
        <Button variant="outline" onClick={() => changeWeek(shiftDate(week, 7))} aria-label="Next week">→</Button></div>
    </div>
    <div className="flex flex-wrap gap-4 text-xs text-slate-600" aria-label="Timetable legend">
      <span className="rounded bg-emerald-100 px-2 py-1 text-emerald-900">Available</span>
      <span className="rounded bg-slate-200 px-2 py-1">Unavailable</span>
      <span className="rounded bg-violet-100 px-2 py-1 text-violet-900">Other clinic</span>
      <span className="rounded border-2 border-sky-600 px-2 py-0.5">Selected</span>
    </div>
    <p className="text-xs text-slate-500">Each drag adds a separate selection. Drag down for a time range or across days to repeat it. Keyboard: select with Enter or Space, use arrow keys to move, Shift + arrows to extend, and Escape to clear. Scroll for all 24 hours.</p>
    <WeeklyTimetable key={`${tenantId}:${doctorId}:${week}`} slots={slots} tenantId={tenantId} doctorId={doctorId} dates={dates} selections={selections}
      onSelect={(next, extend) => { setSelections(previous => updateSelections(previous, next, extend)); setError(''); setMessage('') }} />
    <div className="flex flex-wrap items-center justify-between gap-4 rounded-xl border bg-slate-50 p-4">
      <p className="text-sm" role="status">{selected.length ? `${selected.length} ${selected.length === 1 ? 'slot' : 'slots'} selected · ${selected.length / 2} ${selected.length === 2 ? 'hour' : 'hours'}` : 'Select times on the timetable to get started.'}</p>
      <div className="flex flex-wrap gap-2">
        <Button disabled={!selected.length} onClick={() => apply('add')}>Add availability</Button>
        <Button variant="outline" disabled={!selected.length} onClick={() => apply('remove')}>Remove availability</Button>
        <Button variant="ghost" disabled={!selected.length} onClick={clearFeedback}>Clear selection</Button>
      </div>
    </div>
    {error && <ErrorState message={error} />}
    <p role="status" aria-live="polite" className="text-sm text-emerald-800">{message}</p>
  </section>
}
