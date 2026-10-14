import { AppointmentCell } from './AppointmentCell'
import { dayCells } from './fixtures'
import type { Appointment, AppointmentRole } from './fixtures'

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
  return (
    <div
      aria-label="30-minute appointment cells"
      className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4"
    >
      {dayCells(appointments, date).map((cell) => (
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
