import { readableStatus } from '@/features/appointments/display'
import type { Appointment } from '@/features/scheduling/api'
import { roomEligibility } from '@/features/video/api/admission'
import { useId } from 'react'

export function AppointmentJoinButton({
  appointment,
  role,
  subjectId,
}: {
  appointment: Appointment
  role: 'patient' | 'doctor'
  subjectId: string
}) {
  const reasonId = useId()

  const canJoin = roomEligibility(appointment, role, subjectId)
  let reason = ''
  if (
    appointment[role === 'doctor' ? 'doctor_id' : 'patient_id'] !== subjectId
  ) {
    reason = 'Only the booked patient or doctor can join this consultation.'
  } else if (
    !['held', 'pending_payment', 'confirmed', 'in_progress'].includes(
      appointment.status,
    )
  ) {
    reason = `Video is unavailable for ${readableStatus(appointment.status)} appointments.`
  } else if (
    !['confirmed', 'in_progress'].includes(appointment.status) ||
    appointment.payment_resolution !== 'confirmed' ||
    !appointment.payment_id
  ) {
    reason = 'Joining is available after payment and appointment confirmation.'
  }

  return (
    <div className="space-y-2">
      {canJoin ? (
        <a
          className="inline-block rounded bg-slate-900 px-4 py-3 text-white focus-visible:outline-2 focus-visible:outline-offset-2"
          href={`/${role}/consultation?appointment_id=${encodeURIComponent(appointment.appointment_id)}`}
        >
          Open video consultation
        </a>
      ) : (
        <button
          type="button"
          disabled
          aria-describedby={reasonId}
          className="rounded bg-slate-200 px-4 py-3 text-slate-500 disabled:cursor-not-allowed"
        >
          Open video consultation
        </button>
      )}
      {reason && (
        <p id={reasonId} role="status" className="text-sm text-slate-600">
          {reason}
        </p>
      )}
    </div>
  )
}
