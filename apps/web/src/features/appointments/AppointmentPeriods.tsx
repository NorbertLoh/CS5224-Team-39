import { ErrorState } from '@/components/ErrorState'
import { LoadingState } from '@/components/LoadingState'
import { AppointmentGrid } from '@/features/appointments/AppointmentGrid'
import { LiveAppointmentDetails } from '@/features/appointments/LiveAppointmentDetails'
import type { AppointmentRole } from '@/features/appointments/types'
import type { AppointmentPeriod } from '@/features/scheduling/api'
import { listAppointments, schedulingError } from '@/features/scheduling/api'
import { useInfiniteQuery } from '@tanstack/react-query'
import { Tabs } from 'radix-ui'
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
  const query = useInfiniteQuery({
    queryKey: ['scheduling', 'appointments', token, role, tenantId, period],
    initialPageParam: null as string | null,
    queryFn: ({ pageParam, signal }) =>
      listAppointments(tenantId, pageParam, signal, period),
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
    <Tabs.Root
      value={period}
      onValueChange={(value) => {
        setPeriod(value as AppointmentPeriod)
        setSelectedId(null)
      }}
    >
      <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <Tabs.List
          aria-label="Appointment period"
          className="flex w-fit gap-1 rounded-lg bg-slate-100 p-1"
        >
          {(['upcoming', 'past'] as const).map((value) => (
            <Tabs.Trigger
              key={value}
              value={value}
              className="rounded-md px-4 py-2 text-sm font-medium text-slate-600 data-[state=active]:bg-white data-[state=active]:text-slate-900 data-[state=active]:shadow-sm focus-visible:outline-2 focus-visible:outline-offset-2"
            >
              {value === 'upcoming' ? 'Upcoming' : 'Past'}
            </Tabs.Trigger>
          ))}
        </Tabs.List>
        <button
          className="rounded border px-4 py-2"
          disabled={query.isFetching}
          onClick={() => void query.refetch()}
        >
          Refresh appointments
        </button>
      </div>
      <Tabs.Content
        key={period}
        value={period}
        className="space-y-5 focus-visible:outline-2 focus-visible:outline-offset-2"
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
      </Tabs.Content>
    </Tabs.Root>
  )
}
