import { formatTime, nameOrId, readableStatus } from './display'
import type { AppointmentRole } from './fixtures'
import type { dayCells } from './display'

export function AppointmentCell({
  cell,
  role,
  selectedId,
  onSelect,
}: {
  cell: ReturnType<typeof dayCells>[number]
  role: AppointmentRole
  selectedId: string | null
  onSelect: (id: string) => void
}) {
  return (
    <div className="min-h-24 rounded-lg border bg-slate-50 p-3">
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
              onClick={() => onSelect(appointment.appointment_id)}
            >
              <span className="block font-medium">
                {role === 'patient'
                  ? nameOrId(appointment.doctor_name, appointment.doctor_id)
                  : nameOrId(appointment.patient_name, appointment.patient_id)}
              </span>
              <span className="block text-slate-600">
                {nameOrId(appointment.clinic_name, appointment.tenant_id)}
                {role === 'clinic_admin' &&
                  ` · ${nameOrId(appointment.doctor_name, appointment.doctor_id)}`}
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
  )
}
