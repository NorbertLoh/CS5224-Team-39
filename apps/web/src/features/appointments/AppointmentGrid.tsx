import { AppointmentCell } from './AppointmentCell'
import { dayCells } from './display'
import type { Appointment } from '../scheduling/api'
import type { AppointmentRole } from './types'
import { useAppointmentNames } from './useAppointmentNames'

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
  const namedAppointments = useAppointmentNames(appointments)
  // Show each patient booking once, including its full duration.
  // Staff retain the half-hour timetable for viewing overlapping appointments.
  const cells = role === 'patient'
    ? namedAppointments
        .map((appointment) => ({
          startsAt: appointment.starts_at,
          endsAt: appointment.ends_at,
          appointments: [appointment],
        }))
    : dayCells(namedAppointments, date)
  if (!cells.length)
    return <p className="text-slate-600">{role === 'patient' ? 'No appointments yet.' : 'No appointments on this date.'}</p>
  return (
    <div
      aria-label={role === 'patient' ? 'Appointments' : '30-minute appointment cells'}
      className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4"
    >
      {cells.map((cell) => (
        <AppointmentCell
          key={role === 'patient' ? cell.appointments[0].appointment_id : cell.startsAt}
          cell={cell}
          role={role}
          selectedId={selectedId}
          onSelect={onSelect}
        />
      ))}
    </div>
  )
}
