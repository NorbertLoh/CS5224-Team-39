import { useState } from 'react'
import { ErrorState } from '../../components/ErrorState'
import {
  fixtureClinics,
  fixtureDoctors,
  initialSlots,
  singaporeDate,
} from './fixtures'
import { FixtureSelectors } from './FixtureSelectors'
import { SelectionActions } from './SelectionActions'
import { TimetableToolbar } from './TimetableToolbar'
import {
  applySelection,
  cellsInSelections,
  shiftDate,
  weekStart,
} from './timetable'
import type { Selection } from './timetable'
import { WeeklyTimetable } from './WeeklyTimetable'

export function AvailabilityEditor() {
  const [slots, setSlots] = useState(initialSlots)
  const [tenantId, setTenantId] = useState(fixtureClinics[0].tenant_id)
  const [doctorId, setDoctorId] = useState(
    fixtureDoctors(tenantId)[0].subject_id,
  )
  const [week, setWeek] = useState(() => weekStart(singaporeDate()))
  const [selections, setSelections] = useState<Selection[]>([])
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const dates = Array.from({ length: 7 }, (_, index) => shiftDate(week, index))
  const selectedCount = cellsInSelections(selections, dates).length

  function clearMessages() {
    setError('')
    setMessage('')
  }

  function changeSelection(next: Selection[]) {
    setSelections(next)
    clearMessages()
  }

  function clearSelection() {
    changeSelection([])
  }

  function changeClinic(next: string) {
    setTenantId(next)
    setDoctorId(fixtureDoctors(next)[0].subject_id)
    clearSelection()
  }

  function changeDoctor(next: string) {
    setDoctorId(next)
    clearSelection()
  }

  function changeWeek(next: string) {
    setWeek(next)
    clearSelection()
  }

  function apply(action: 'add' | 'remove') {
    if (!selections.length) return
    clearMessages()

    try {
      const nextSlots = applySelection(
        slots,
        tenantId,
        doctorId,
        selections,
        dates,
        action,
      )
      setSlots(nextSlots)
      setSelections([])
      setMessage(
        action === 'add'
          ? `${selectedCount} slots added to the fixture schedule.`
          : 'Selected availability removed from the fixture schedule.',
      )
    } catch (cause) {
      setError((cause as Error).message)
    }
  }

  return (
    <section className="mt-8 space-y-5" aria-labelledby="availability-heading">
      <div>
        <h2 id="availability-heading" className="text-2xl font-semibold">
          Your availability
        </h2>
        <p className="mt-2 text-slate-600">
          Drag across the timetable to select consultation times, then add or
          remove availability.
        </p>
      </div>
      <FixtureSelectors
        tenantId={tenantId}
        doctorId={doctorId}
        onClinicChange={changeClinic}
        onDoctorChange={changeDoctor}
      />
      <TimetableToolbar week={week} onWeekChange={changeWeek} />
      <WeeklyTimetable
        key={`${tenantId}:${doctorId}:${week}`}
        slots={slots}
        tenantId={tenantId}
        doctorId={doctorId}
        dates={dates}
        selections={selections}
        onChange={changeSelection}
      />
      <SelectionActions
        count={selectedCount}
        onAdd={() => apply('add')}
        onRemove={() => apply('remove')}
        onClear={clearSelection}
      />
      {error && <ErrorState message={error} />}
      <p role="status" aria-live="polite" className="text-sm text-emerald-800">
        {message}
      </p>
    </section>
  )
}
