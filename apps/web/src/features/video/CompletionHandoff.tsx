import { useQuery } from '@tanstack/react-query'
import type { Appointment } from '../scheduling/api'
import { readMedicalCertificate } from '../records/api'
import { ConsultationActions } from './ConsultationActions'

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
