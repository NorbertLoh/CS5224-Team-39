import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import type { Appointment } from '../scheduling/api'
import { consultationAction, consultationError } from './admission'
import { readMedicalCertificate } from '../records/api'

export function CompletionHandoff({
  appointment,
  token,
}: {
  appointment: Appointment
  token: string
}) {
  const mc = useQuery({
    queryKey: ['records', 'mc', token, appointment.appointment_id],
    queryFn: ({ signal }) =>
      readMedicalCertificate(appointment.appointment_id, signal),
    retry: false,
    gcTime: 0,
  })
  if (mc.isPending) return <p role="status">Checking completion handoff...</p>
  if (mc.data?.finalized_at)
    return (
      <p role="status">Consultation completion and MC decision confirmed.</p>
    )
  return (
    <>
      <p role="alert">
        The saved MC decision has not been confirmed. Retry the completion
        handoff to check and finalize it.
      </p>
      <ConsultationActions appointment={appointment} />
    </>
  )
}

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
        ['consultation', 'records', 'scheduling', 'documents'].map((key) =>
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
        the appointment. Save any MC draft first. If completion reports an error
        after the appointment ends, retry the completion handoff below to
        finalize the saved MC decision.
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
            : appointment.status === 'completed'
              ? 'Retry completion handoff'
              : 'Complete consultation'}
      </button>
      {mutation.isError && (
        <p role="alert">
          {consultationError(mutation.error)} Refresh to check the appointment
          before retrying.
        </p>
      )}
      {mutation.isSuccess && (
        <p role="status">
          {action === 'complete'
            ? 'Consultation completion and MC decision confirmed. Refresh Documents for PDF status.'
            : 'Consultation started.'}
        </p>
      )}
    </section>
  )
}
