import { useMutation, useQueryClient } from '@tanstack/react-query'
import type { Appointment } from '../scheduling/api'
import { consultationAction, consultationError } from './admission'

export function ConsultationActions({
  appointment,
}: {
  appointment: Appointment
}) {
  const cache = useQueryClient()
  const action = appointment.status === 'confirmed' ? 'start' : 'complete'
  const mutation = useMutation({
    mutationFn: () => consultationAction(appointment.appointment_id, action),
    onSettled: async () => {
      await Promise.all(
        ['consultation', 'records', 'scheduling'].map((key) =>
          cache.invalidateQueries({ queryKey: [key] }),
        ),
      )
    },
    retry: false,
  })
  return (
    <section
      className="mx-auto max-w-[1600px] space-y-3 px-4 pt-6 sm:px-8"
      aria-label="Consultation lifecycle"
    >
      <p>
        Start the consultation to enable clinical writing. Completing it ends
        room access for both participants. Leaving video alone does not complete
        the appointment.
      </p>
      <button
        className="rounded border px-4 py-2"
        disabled={
          mutation.isPending ||
          (action === 'start' && Date.now() < Date.parse(appointment.starts_at))
        }
        onClick={() => mutation.mutate()}
      >
        {mutation.isPending
          ? 'Updating consultation...'
          : action === 'start'
            ? 'Start clinical consultation'
            : 'Complete consultation'}
      </button>
      {mutation.isError && (
        <p role="alert">
          {consultationError(mutation.error)} Refresh to check the appointment
          before retrying.
        </p>
      )}
    </section>
  )
}
