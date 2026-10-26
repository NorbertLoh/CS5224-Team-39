import { useEffect, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import type { Appointment } from '../scheduling/api'
import { consultationAction, consultationError } from './admission'
import { joinEarlyMinutes } from './joinWindow'

export function ConsultationActions({
  appointment,
}: {
  appointment: Appointment
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
  return (
    <section
      className="mb-6 space-y-3 rounded-xl border bg-white p-6 text-sm"
      aria-label="Consultation lifecycle"
    >
      <p>
        Start the consultation to enable clinical writing. Completing it ends
        room access for both participants. Leaving video alone does not complete
        the appointment. Save any MC draft first. If completion reports an error
        after the appointment ends, retry the completion handoff below to
        finalize the saved MC decision.
      </p>
      <button
        className="rounded border px-4 py-2"
        disabled={mutation.isPending || tooEarly}
        aria-describedby={tooEarly ? 'clinical-start-time' : undefined}
        onClick={() => mutation.mutate(action)}
      >
        {mutation.isPending
          ? 'Updating consultation...'
          : action === 'start'
            ? 'Start clinical consultation'
            : appointment.status === 'completed'
              ? 'Retry completion handoff'
              : 'Complete consultation'}
      </button>
      {tooEarly && (
        <p id="clinical-start-time" role="status">
          Clinical start opens at{' '}
          {new Date(opensAt).toLocaleString('en-SG', { timeZone: 'Asia/Singapore' })} SGT.
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
            ? 'Consultation completion and MC decision confirmed. Refresh Documents for PDF status.'
            : 'Consultation started.'}
        </p>
      )}
    </section>
  )
}
