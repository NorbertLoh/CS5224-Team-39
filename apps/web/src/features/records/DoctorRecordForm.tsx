import { useState } from 'react'
import { useInfiniteQuery } from '@tanstack/react-query'
import { listAppointments } from '../scheduling/api'
import { useSchedulingIdentity } from '../scheduling/useSchedulingIdentity'
import { RecordWorkspace } from './RecordWorkspace'
import { nameOrId, readableStatus } from '../appointments/display'
import { recordsError } from './api'
import { ErrorState } from '../../components/ErrorState'
import { LoadingState } from '../../components/LoadingState'

export function DoctorRecordForm() {
  const identity = useSchedulingIdentity()
  if (identity.isError)
    return (
      <ErrorState
        message="Could not verify records access."
        onRetry={() => void identity.refetch()}
      />
    )
  if (!identity.data || !identity.token)
    return <LoadingState message="Loading records access..." />
  return (
    <DoctorAppointments
      key={identity.token}
      token={identity.token}
      subjectId={identity.data.subject_id}
    />
  )
}

function DoctorAppointments({
  token,
  subjectId,
}: {
  token: string
  subjectId: string
}) {
  const [selected, setSelected] = useState('')
  const query = useInfiniteQuery({
    queryKey: ['records', 'appointments', token],
    initialPageParam: null as string | null,
    queryFn: ({ pageParam, signal }) =>
      listAppointments(undefined, pageParam, signal),
    getNextPageParam: (page) => page.next_cursor ?? undefined,
    retry: false,
    gcTime: 0,
  })
  const appointments =
    query.data?.pages
      .flatMap((page) => page.items)
      .filter((item) => item.doctor_id === subjectId) ?? []
  return (
    <section
      className="space-y-5 rounded-xl border bg-white p-6"
      aria-labelledby="record-heading"
    >
      <h2 id="record-heading" className="text-xl font-semibold">
        Consultation notes and prescription
      </h2>
      <p className="text-sm text-slate-600">
        Choose an appointment to read or save its clinical records. Writing is
        available only during an in-progress consultation.
      </p>
      {query.isPending ? (
        <LoadingState message="Loading your appointments..." />
      ) : query.isError ? (
        <ErrorState
          message={recordsError(query.error)}
          onRetry={() => void query.refetch()}
        />
      ) : (
        <>
          {!appointments.length && (
            <p role="status">No appointments available.</p>
          )}
          <label className="flex flex-col gap-2">
            Appointment
            <select
              className="rounded border p-2"
              value={selected}
              onChange={(event) => setSelected(event.target.value)}
            >
              <option value="">Select an appointment</option>
              {appointments.map((item) => (
                <option key={item.appointment_id} value={item.appointment_id}>
                  {new Intl.DateTimeFormat('en-SG', {
                    timeZone: 'Asia/Singapore',
                    dateStyle: 'medium',
                    timeStyle: 'short',
                  }).format(new Date(item.starts_at))}{' '}
                  SGT · {nameOrId(item.patient_name, item.patient_id)} ·{' '}
                  {readableStatus(item.status)}
                </option>
              ))}
            </select>
          </label>
          <p className="text-sm text-slate-600">
            Switching appointments discards unsaved changes.
          </p>
          {query.hasNextPage && (
            <button
              className="rounded border px-4 py-2"
              disabled={query.isFetchingNextPage}
              onClick={() => void query.fetchNextPage()}
            >
              Load more appointments
            </button>
          )}
          {selected &&
            appointments.some((item) => item.appointment_id === selected) && (
              <RecordWorkspace
                key={selected}
                appointmentId={selected}
                token={token}
                subjectId={subjectId}
              />
            )}
        </>
      )}
    </section>
  )
}
