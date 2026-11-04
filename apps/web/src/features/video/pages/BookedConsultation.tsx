import { ErrorState } from '@/components/ErrorState'
import { LoadingState } from '@/components/LoadingState'
import { DocumentList } from '@/features/documents/DocumentList'
import { appointmentDetail } from '@/features/scheduling/api'
import { useSchedulingIdentity } from '@/features/scheduling/useSchedulingIdentity'
import {
  bookedRoomConnection,
  consultationError,
  roomAccessDenied,
  roomEligibility,
} from '@/features/video/api/admission'
import { CompletionHandoff } from '@/features/video/components/CompletionHandoff'
import { ConsultationActions } from '@/features/video/components/ConsultationActions'
import { VideoRoom } from '@/features/video/room/VideoRoom'
import { useQuery } from '@tanstack/react-query'
import { useMemo } from 'react'

export function BookedConsultation({ role }: { role: 'patient' | 'doctor' }) {
  const id =
    new URLSearchParams(window.location.search).get('appointment_id') ?? ''
  const identity = useSchedulingIdentity(true)
  const appointment = useQuery({
    queryKey: ['consultation', 'appointment', identity.cacheKey, id],
    queryFn: ({ signal }) => appointmentDetail(id, signal),
    enabled: Boolean(id && identity.data && identity.token),
    refetchInterval: 5000,
    retry: false,
    gcTime: 0,
  })
  const subject = identity.data?.subject_id ?? ''
  const setup = useMemo(() => {
    if (!id || !subject) return {}
    try {
      return { connection: bookedRoomConnection(id, subject) }
    } catch {
      return {
        error: 'Open the application through its HTTPS consultation address.',
      }
    }
  }, [id, subject])
  if (!id)
    return (
      <main className="mx-auto max-w-3xl space-y-4 px-6 py-10">
        <h1 className="text-2xl font-semibold">Choose a booked appointment</h1>
        <p>Open your appointment details to enter its video consultation.</p>
        <a className="underline" href={`/${role}`}>
          Back to appointments
        </a>
      </main>
    )
  if (
    (identity.isError &&
      (!identity.data || roomAccessDenied(identity.error))) ||
    (appointment.isError &&
      (!appointment.data || roomAccessDenied(appointment.error)))
  )
    return (
      <ErrorState
        message={consultationError(identity.error ?? appointment.error)}
        onRetry={() => {
          void identity.refetch()
          void appointment.refetch()
        }}
      />
    )
  if (!identity.data || !identity.token || !appointment.data)
    return <LoadingState message="Checking your booked appointment..." />
  if (
    appointment.data.appointment_id === id &&
    appointment.data.status === 'completed' &&
    appointment.data[role === 'doctor' ? 'doctor_id' : 'patient_id'] === subject
  )
    return (
      <main className="mx-auto max-w-3xl space-y-4 px-6 py-10">
        <h1 className="text-2xl font-semibold">Consultation completed</h1>
        <p>This appointment has ended.</p>
        {role === 'doctor' && (
          <CompletionHandoff
            appointment={appointment.data}
            token={identity.token}
          />
        )}
        <DocumentList
          role={role}
          appointmentId={id}
          tenantId={appointment.data.tenant_id}
          autoRefresh={role === 'doctor'}
        />
        <a className="underline" href={`/${role}`}>
          Back to appointments
        </a>
      </main>
    )
  if (
    appointment.data.appointment_id !== id ||
    !roomEligibility(appointment.data, role, subject)
  )
    return (
      <ErrorState message="This appointment is not ready for video. Calls require confirmed payment, an unfinished consultation and current participant access." />
    )
  if (setup.error || !setup.connection)
    return (
      <ErrorState message={setup.error ?? 'Call configuration unavailable.'} />
    )
  return (
    <VideoRoom
      key={`${id}:${subject}:${identity.cacheKey}`}
      role={role}
      connection={setup.connection}
      appointmentId={id}
      token={identity.token}
      subjectId={subject}
      actions={
        role === 'doctor' &&
        appointment.data.status === 'confirmed' && (
          <ConsultationActions appointment={appointment.data} />
        )
      }
      endActions={
        role === 'doctor' && appointment.data.status === 'in_progress'
          ? (blocked, onPendingChange) => (
              <ConsultationActions
                appointment={appointment.data}
                disabled={blocked}
                onPendingChange={onPendingChange}
              />
            )
          : undefined
      }
    />
  )
}
