import { useState } from 'react'
import { AppointmentDetails } from './AppointmentDetails'
import {
  appointmentDates,
  clinicName,
  dateInSingapore,
  dayCells,
  formatDate,
  formatTime,
  previewContexts,
  readableStatus,
  scopedAppointments,
  subjectName,
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
      <div className="flex flex-wrap gap-4">
        <label className="flex flex-col gap-1 text-sm font-medium">
          {role === 'clinic_admin' ? 'Demo clinic' : `Demo ${role}`}
          <select
            className="rounded border bg-white px-3 py-2"
            value={contextId}
            onChange={(event) => {
              setContextId(event.target.value)
              setSelectedId(null)
              setSelectedDate('')
            }}
          >
            {contexts.map((context) => (
              <option key={context.id} value={context.id}>
                {context.name}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-sm font-medium">
          Date
          <select
            className="rounded border bg-white px-3 py-2"
            value={date}
            onChange={(event) => {
              setSelectedDate(event.target.value)
              setSelectedId(null)
            }}
          >
            {dates.map((item) => (
              <option key={item} value={item}>
                {formatDate(item)}
              </option>
            ))}
          </select>
        </label>
      </div>
      <p role="status" className="text-sm text-slate-600">
        {day.length
          ? `${day.length} appointments on ${formatDate(date)}.`
          : 'No appointments on this date.'}
      </p>
      <div
        aria-label="30-minute appointment cells"
        className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4"
      >
        {dayCells(appointments, date).map((cell) => (
          <div
            key={cell.startsAt}
            className="min-h-24 rounded-lg border bg-slate-50 p-3"
          >
            <p className="mb-2 text-sm font-medium text-slate-600">
              {formatTime(cell.startsAt)}–{formatTime(cell.endsAt)}
            </p>
            {cell.appointments.length ? (
              <div className="space-y-2">
                {cell.appointments.map((appointment) => (
                  <button
                    key={appointment.appointment_id}
                    type="button"
                    aria-pressed={selectedId === appointment.appointment_id}
                    className={`w-full rounded border p-3 text-left text-sm focus-visible:outline-2 focus-visible:outline-offset-2 ${selectedId === appointment.appointment_id ? 'border-teal-700 bg-teal-100' : 'border-slate-200 bg-white hover:border-teal-600'}`}
                    onClick={() => setSelectedId(appointment.appointment_id)}
                  >
                    <span className="block font-medium">
                      {subjectName(
                        role === 'patient'
                          ? appointment.doctor_id
                          : appointment.patient_id,
                      )}
                    </span>
                    <span className="block text-slate-600">
                      {clinicName(appointment.tenant_id)}
                      {role === 'clinic_admin' &&
                        ` · ${subjectName(appointment.doctor_id)}`}
                    </span>
                    <span className="mt-1 block capitalize">
                      {readableStatus(appointment.status)}
                    </span>
                  </button>
                ))}
              </div>
            ) : (
              <span className="text-sm text-slate-400">No appointment</span>
            )}
          </div>
        ))}
      </div>
      {selected && (
        <AppointmentDetails
          appointment={selected}
          onClose={() => setSelectedId(null)}
        />
      )}
    </section>
  )
}
