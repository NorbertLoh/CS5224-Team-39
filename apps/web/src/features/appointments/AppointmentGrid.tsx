import { AppointmentCell } from './AppointmentCell'
import { dayCells } from './display'
import type { Appointment } from '../scheduling/api'
import type { AppointmentRole } from './types'

export function AppointmentGrid({
  appointments,
  date,
  role,
  selectedId,
  onSelect,
}: {
  appointments: Appointment[]
  date: string
  role: AppointmentRole
  selectedId: string | null
  onSelect: (id: string) => void
}) {
  // Patients only need their own bookings; staff see the full day timetable.
  const cells = dayCells(appointments, date).filter(
    (cell) => role !== 'patient' || cell.appointments.length,
  )
  if (!cells.length)
    return <p className="text-slate-600">No appointments on this date.</p>
  return (
    <div
      aria-label="30-minute appointment cells"
      className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4"
    >
      {cells.map((cell) => (
        <AppointmentCell
          key={cell.startsAt}
          cell={cell}
          role={role}
          selectedId={selectedId}
          onSelect={onSelect}
        />
      ))}
    </div>
  )
}
