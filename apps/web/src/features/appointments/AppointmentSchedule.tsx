import { AppointmentFilters } from './AppointmentFilters'
import { AppointmentGrid } from './AppointmentGrid'
import { useState } from 'react'
import { AppointmentDetails } from './AppointmentDetails'
import {
  appointmentDates,
  dateInSingapore,
  formatDate,
  previewContexts,
  scopedAppointments,
} from './fixtures'
import type { AppointmentRole } from './fixtures'

export function AppointmentSchedule({
  role,
  tenantId,
}: {
  role: AppointmentRole
  tenantId?: string
}) {
  const contexts = previewContexts(role).filter(
    (context) =>
      role !== 'clinic_admin' || !tenantId || context.id === tenantId,
  )
  const [contextId, setContextId] = useState(contexts[0]?.id ?? '')
  const appointments = scopedAppointments(role, contextId, tenantId)
  const dates = appointmentDates(appointments)
  const [selectedDate, setSelectedDate] = useState(dates[0])
  const date = dates.includes(selectedDate) ? selectedDate : dates[0]
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const selected = appointments.find(
    (item) =>
      item.appointment_id === selectedId &&
      dateInSingapore(item.starts_at) === date,
  )
  const day = appointments.filter(
    (item) => dateInSingapore(item.starts_at) === date,
  )

  return (
    <section aria-labelledby="appointments-heading" className="mt-8 space-y-5">
      <div>
        <h2 id="appointments-heading" className="text-2xl font-semibold">
          Appointments
        </h2>
        <p className="mt-2 text-slate-600">
          Choose a date, then select an appointment to see its details. All
          times are Singapore time (SGT).
        </p>
        <p className="mt-2 rounded bg-amber-50 p-3 text-sm text-amber-900">
          Fixture preview — synthetic appointments, not your live schedule.
          Empty cells are not booking availability.
        </p>
      </div>
      <AppointmentFilters
        role={role}
        contexts={contexts}
        contextId={contextId}
        dates={dates}
        date={date}
        onContextChange={(id) => {
          setContextId(id)
          setSelectedId(null)
          setSelectedDate('')
        }}
        onDateChange={(value) => {
          setSelectedDate(value)
          setSelectedId(null)
        }}
      />
      <p role="status" className="text-sm text-slate-600">
        {day.length
          ? `${day.length} appointments on ${formatDate(date)}.`
          : 'No appointments on this date.'}
      </p>
      <AppointmentGrid
        appointments={appointments}
        date={date}
        role={role}
        selectedId={selectedId}
        onSelect={setSelectedId}
      />
      {selected && (
        <AppointmentDetails
          appointment={selected}
          onClose={() => setSelectedId(null)}
        />
      )}
    </section>
  )
}
