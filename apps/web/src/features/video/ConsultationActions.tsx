import { useEffect, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import type { Appointment } from '../scheduling/api'
import { consultationAction, consultationError } from './admission'
import { joinEarlyMinutes } from './joinWindow'

export function ConsultationActions({
  appointment,
  disabled = false,
  onPendingChange,
}: {
  appointment: Appointment
  disabled?: boolean
  onPendingChange?: (pending: boolean) => void
}) {
  const cache = useQueryClient()
  const [now, setNow] = useState(Date.now)
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(timer)
  }, [])
  const earlyMinutes = joinEarlyMinutes > 10 ? joinEarlyMinutes : 0
  const opensAt = Date.parse(appointment.starts_at) - earlyMinutes * 60000
  const action = appointment.status === 'confirmed' ? 'start' : 'complete'
  const tooEarly = action === 'start' && now < opensAt
  const mutation = useMutation({
    mutationFn: (requested: 'start' | 'complete') =>
      consultationAction(appointment.appointment_id, requested),
    onSettled: async () => {
      await Promise.all(
        ['consultation', 'records', 'scheduling', 'documents'].map((key) =>
          cache.invalidateQueries({ queryKey: [key] }),
        ),
      )
    },
    retry: false,
  })
  useEffect(() => {
    onPendingChange?.(mutation.isPending)
    return () => onPendingChange?.(false)
  }, [mutation.isPending, onPendingChange])
  return (
    <section
      className="space-y-3 rounded-xl border bg-white p-5 text-sm"
      aria-label="Consultation lifecycle"
    >
      <p>
        {action === 'start'
          ? 'Start the consultation to enable clinical notes, prescriptions and MC drafts.'
          : disabled
            ? 'Wait for your draft changes to save before ending the consultation.'
            : 'Ending issues your saved prescription, completes the consultation and finalises the MC decision. Leaving video alone does not end the consultation.'}
      </p>
      <button
        className={`rounded-lg px-5 py-3 font-medium disabled:opacity-50 ${action === 'start' ? 'bg-teal-800 text-white' : 'bg-red-50 text-red-800 border border-red-200'}`}
        disabled={disabled || mutation.isPending || tooEarly}
        aria-describedby={tooEarly ? 'clinical-start-time' : undefined}
        onClick={() => mutation.mutate(action)}
      >
        {mutation.isPending
          ? action === 'complete'
            ? 'Finishing consultation...'
            : 'Starting consultation...'
          : action === 'start'
            ? 'Start consultation'
            : appointment.status === 'completed'
              ? 'Retry completion handoff'
              : 'End consultation'}
      </button>
      {tooEarly && (
        <p id="clinical-start-time" role="status">
          Clinical start opens at{' '}
          {new Date(opensAt).toLocaleString('en-SG', {
            timeZone: 'Asia/Singapore',
          })}{' '}
          SGT.
        </p>
      )}
      {mutation.isError && (
        <p role="alert">
          {consultationError(mutation.error)} Refresh to check the appointment
          before retrying.
        </p>
      )}
      {mutation.isSuccess && (
        <p role="status">
          {mutation.variables === 'complete'
            ? 'Prescription, consultation completion and MC decision confirmed. Refresh Documents for PDF status.'
            : 'Consultation started.'}
        </p>
      )}
    </section>
  )
}
