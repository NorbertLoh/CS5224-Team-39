import { AppointmentCell } from '@/features/appointments/AppointmentCell'
import { dayCells } from '@/features/appointments/display'
import type { AppointmentRole } from '@/features/appointments/types'
import { useAppointmentNames } from '@/features/appointments/useAppointmentNames'
import type { Appointment } from '@/features/scheduling/api'

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
  // Across-date lists show each booking once, including its full duration.
  const cards = role === 'patient' || !date
  const cells = cards
    ? namedAppointments.map((appointment) => ({
        startsAt: appointment.starts_at,
        endsAt: appointment.ends_at,
        appointments: [appointment],
      }))
    : dayCells(namedAppointments, date)
  if (!cells.length)
    return (
      <p className="text-slate-600">
        {cards ? 'No appointments yet.' : 'No appointments on this date.'}
      </p>
    )
  return (
    <div
      aria-label={cards ? 'Appointments' : '30-minute appointment cells'}
      className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4"
    >
      {cells.map((cell) => (
        <AppointmentCell
          key={cards ? cell.appointments[0].appointment_id : cell.startsAt}
          cell={cell}
          role={role}
          showDate={cards}
          selectedId={selectedId}
          onSelect={onSelect}
        />
      ))}
    </div>
  )
}
