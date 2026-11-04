import { ErrorState } from '@/components/ErrorState'
import { LoadingState } from '@/components/LoadingState'
import { AppointmentGrid } from '@/features/appointments/AppointmentGrid'
import { LiveAppointmentDetails } from '@/features/appointments/LiveAppointmentDetails'
import type { AppointmentRole } from '@/features/appointments/types'
import type { AppointmentPeriod } from '@/features/scheduling/api'
import {
  appointmentCounts,
  listAppointments,
  schedulingError,
} from '@/features/scheduling/api'
import { useInfiniteQuery, useQuery } from '@tanstack/react-query'
import { CountTabs } from '@/components/CountTabs'
import { ListFilters } from '@/components/ListFilters'
import { emptyFilters } from '@/lib/list-filters'
import { useState } from 'react'

export function AppointmentPeriods({
  role,
  tenantId,
  token,
  subjectId,
}: {
  role: AppointmentRole
  tenantId?: string
  token?: string
  subjectId: string
}) {
  const [period, setPeriod] = useState<AppointmentPeriod>('upcoming')
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [filters, setFilters] = useState(emptyFilters)
  const counts = useQuery({
    queryKey: [
      'scheduling',
      'appointments',
      'counts',
      token,
      role,
      tenantId,
      filters,
    ],
    queryFn: ({ signal }) => appointmentCounts(tenantId, filters, signal, role),
    refetchInterval: 15000,
    retry: false,
  })
  const query = useInfiniteQuery({
    queryKey: [
      'scheduling',
      'appointments',
      token,
      role,
      tenantId,
      period,
      filters,
    ],
    initialPageParam: null as string | null,
    queryFn: ({ pageParam, signal }) =>
      listAppointments(tenantId, pageParam, signal, period, filters, role),
    getNextPageParam: (page) => page.next_cursor ?? undefined,
    refetchInterval: 15000,
    refetchOnWindowFocus: true,
    retry: false,
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
  return (
    <>
      <ListFilters
        value={filters}
        onApply={(value) => {
          setFilters(value)
          setSelectedId(null)
        }}
        dateLabel="Appointment"
        placeholder="Patient, doctor, clinic name or appointment ID"
        statuses={{
          held: 'Held',
          pending_payment: 'Pending payment',
          confirmed: 'Confirmed',
          in_progress: 'In progress',
          completed: 'Completed',
          cancelled: 'Cancelled',
          expired: 'Expired',
          no_show: 'No show',
        }}
      />
      {counts.isError && (
        <ErrorState
          message="Could not refresh appointment counts."
          onRetry={() => void counts.refetch()}
        />
      )}
      <div className="mb-4 flex flex-wrap justify-between gap-3">
        <p className="text-sm text-slate-600" aria-live="polite">
          {counts.data?.total ?? '—'} matching appointments
        </p>
        <button
          className="rounded border px-4 py-2"
          disabled={query.isFetching || counts.isFetching}
          onClick={() => {
            void query.refetch()
            void counts.refetch()
          }}
        >
          Refresh appointments
        </button>
      </div>
      <CountTabs
        value={period}
        onChange={(value) => {
          setPeriod(value as AppointmentPeriod)
          setSelectedId(null)
        }}
        label="Appointment period"
        items={[
          { value: 'upcoming', label: 'Upcoming' },
          { value: 'past', label: 'Past' },
        ]}
        counts={counts.data}
      >
        <p className="text-sm text-slate-600">
          {period === 'upcoming'
            ? 'Active and ongoing appointments, soonest first.'
            : 'Ended, cancelled and expired appointments, most recent appointment date first.'}
        </p>
        {query.isPending ? (
          <LoadingState message="Loading appointments..." />
        ) : query.isError ? (
          <ErrorState
            message={schedulingError(query.error)}
            onRetry={() => void query.refetch()}
          />
        ) : (
          <>
            {appointments.length ? (
              <>
                <p role="status" className="text-sm text-slate-600">
                  {appointments.length}{' '}
                  {appointments.length === 1 ? 'appointment' : 'appointments'}{' '}
                  shown
                  {query.hasNextPage ? '; more available.' : '.'}
                </p>
                <AppointmentGrid
                  appointments={appointments}
                  date=""
                  role={role}
                  selectedId={selectedId}
                  onSelect={setSelectedId}
                />
              </>
            ) : (
              <p role="status" className="text-slate-600">
                No {period} appointments.
              </p>
            )}
            {query.hasNextPage && (
              <button
                className="rounded border px-4 py-2"
                disabled={query.isFetching}
                onClick={() => void query.fetchNextPage()}
              >
                Load more appointments
              </button>
            )}
            {selectedId &&
              appointments.some((a) => a.appointment_id === selectedId) && (
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
      </CountTabs>
    </>
  )
}
