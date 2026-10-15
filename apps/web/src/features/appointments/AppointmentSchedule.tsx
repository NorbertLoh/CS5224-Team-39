import { useState } from 'react'
import { useInfiniteQuery } from '@tanstack/react-query'
import { AppointmentGrid } from './AppointmentGrid'
import { LiveAppointmentDetails } from './LiveAppointmentDetails'
import type { AppointmentRole } from './fixtures'
import { dateInSingapore, formatDate } from './display'
import { listAppointments, schedulingError } from '../scheduling/api'
import { singaporeDate } from '../scheduling/time'
import { useSchedulingIdentity } from '../scheduling/useSchedulingIdentity'
import { ErrorState } from '../../components/ErrorState'
import { LoadingState } from '../../components/LoadingState'

export function AppointmentSchedule({
  role,
  tenantId,
}: {
  role: AppointmentRole
  tenantId?: string
}) {
  const identity = useSchedulingIdentity()
  const [selectedClinic, setSelectedClinic] = useState('')
  const memberships =
    identity.data?.memberships.filter(
      (member) => member.status === 'active' && member.roles.includes(role),
    ) ?? []
  const clinic =
    tenantId ??
    (role === 'clinic_admin'
      ? memberships.some((member) => member.tenant_id === selectedClinic)
        ? selectedClinic
        : memberships[0]?.tenant_id
      : undefined)
  if (identity.isError)
    return (
      <ErrorState
        message="Could not verify appointment access."
        onRetry={() => void identity.refetch()}
      />
    )
  if (!identity.data)
    return <LoadingState message="Loading appointment access..." />
  if (
    role === 'clinic_admin' &&
    !memberships.some((member) => member.tenant_id === clinic)
  )
    return (
      <p role="status">No active clinic admin membership for this clinic.</p>
    )
  return (
    <section aria-labelledby="appointments-heading" className="mt-8 space-y-5">
      <h2 id="appointments-heading" className="text-2xl font-semibold">
        Appointments
      </h2>
      <p className="text-slate-600">
        Choose a date, then select an appointment to see its details. All times
        are Singapore time (SGT).
      </p>
      {role === 'clinic_admin' && !tenantId && (
        <label className="flex max-w-sm flex-col gap-2">
          Clinic
          <select
            className="rounded border bg-white p-2"
            value={clinic}
            onChange={(event) => setSelectedClinic(event.target.value)}
          >
            {memberships.map((member) => (
              <option key={member.tenant_id} value={member.tenant_id}>
                {member.tenant_id}
              </option>
            ))}
          </select>
        </label>
      )}
      <LiveSchedule
        key={`${identity.token}:${role}:${clinic ?? ''}`}
        role={role}
        tenantId={clinic}
        subjectId={identity.data.subject_id}
        token={identity.token}
      />
    </section>
  )
}

function LiveSchedule({
  role,
  tenantId,
  subjectId,
  token,
}: {
  role: AppointmentRole
  tenantId?: string
  subjectId: string
  token?: string
}) {
  const [selectedDate, setSelectedDate] = useState('')
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const query = useInfiniteQuery({
    queryKey: ['scheduling', 'appointments', token, tenantId],
    initialPageParam: null as string | null,
    queryFn: ({ pageParam, signal }) =>
      listAppointments(tenantId, pageParam, signal),
    getNextPageParam: (page) => page.next_cursor ?? undefined,
    refetchInterval: 15000,
    refetchOnWindowFocus: true,
  })
  const appointments = (
    query.data?.pages.flatMap((page) => page.items) ?? []
  ).filter((appointment) =>
    role === 'patient'
      ? appointment.patient_id === subjectId
      : role === 'doctor'
        ? appointment.doctor_id === subjectId
        : appointment.tenant_id === tenantId,
  )
  const date =
    selectedDate ||
    (appointments[0]
      ? dateInSingapore(appointments[0].starts_at)
      : singaporeDate())
  const dates = [
    ...new Set([
      singaporeDate(),
      date,
      ...appointments.map((item) => dateInSingapore(item.starts_at)),
    ]),
  ].sort()
  return (
    <>
      <div className="flex flex-wrap gap-4">
        <label className="flex flex-col gap-2">
          Date
          <select
            className="rounded border bg-white p-2"
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
        <button
          className="self-end rounded border px-4 py-2"
          disabled={query.isFetching}
          onClick={() => void query.refetch()}
        >
          Refresh appointments
        </button>
      </div>
      {query.isPending ? (
        <LoadingState message="Loading live appointments..." />
      ) : query.isError ? (
        <ErrorState
          message={schedulingError(query.error)}
          onRetry={() => void query.refetch()}
        />
      ) : (
        <>
          <p role="status">
            {
              appointments.filter(
                (item) => dateInSingapore(item.starts_at) === date,
              ).length
            }{' '}
            appointments on {formatDate(date)}. Empty cells are not booking
            availability.
          </p>
          <AppointmentGrid
            appointments={appointments}
            date={date}
            role={role}
            selectedId={selectedId}
            onSelect={setSelectedId}
          />
          {query.hasNextPage && (
            <button
              className="rounded border px-4 py-2"
              disabled={query.isFetchingNextPage}
              onClick={() => void query.fetchNextPage()}
            >
              Load more appointments and dates
            </button>
          )}
          {selectedId && (
            <LiveAppointmentDetails
              key={selectedId}
              id={selectedId}
              token={token}
              subjectId={subjectId}
              role={role}
              onClose={() => setSelectedId(null)}
            />
          )}
        </>
      )}
    </>
  )
}
