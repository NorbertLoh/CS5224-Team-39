import { ErrorState } from '@/components/ErrorState'
import { LoadingState } from '@/components/LoadingState'
import { Button } from '@/components/ui/button'
import {
  clinicStatuses,
  listAdminClinics,
} from '@/features/platform-clinics/api'
import { useInfiniteQuery } from '@tanstack/react-query'
import { useState } from 'react'

export function ClinicList({ token }: { token: string }) {
  const [status, setStatus] = useState('pending_review')
  const clinics = useInfiniteQuery({
    queryKey: ['platform-clinics', token, status],
    initialPageParam: null as string | null,
    queryFn: ({ pageParam, signal }) =>
      listAdminClinics(status, pageParam, signal),
    getNextPageParam: (page) => page.next_cursor ?? undefined,
  })

  return (
    <section className="mt-8" aria-label="Platform clinics">
      <label className="grid max-w-xs gap-2 text-sm font-medium">
        Clinic status
        <select
          value={status}
          onChange={(event) => setStatus(event.target.value)}
          className="rounded-md border bg-white p-2"
        >
          <option value="">All statuses</option>
          {Object.entries(clinicStatuses).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
      </label>
      {clinics.isPending ? (
        <LoadingState message="Loading clinics..." />
      ) : clinics.isError ? (
        <ErrorState
          message="Could not load clinics. Check your platform access and backend connection."
          onRetry={() => void clinics.refetch()}
        />
      ) : (
        <>
          {!clinics.data.pages.some((page) => page.items.length) && (
            <p className="mt-6">No clinics with this status.</p>
          )}
          <ul className="mt-6 grid gap-3">
            {clinics.data.pages
              .flatMap((page) => page.items)
              .map((clinic) => (
                <li key={clinic.tenant_id}>
                  <a
                    href={`/platform-admin/clinics/${clinic.tenant_id}`}
                    className="flex flex-wrap items-center justify-between gap-4 rounded-xl border bg-white p-5 hover:bg-slate-100 focus-visible:outline-2"
                  >
                    <div>
                      <h2 className="font-semibold">{clinic.name}</h2>
                      <p className="mt-1 text-sm text-slate-600">
                        {clinicStatuses[clinic.status]} · Commission{' '}
                        {clinic.commission_bps / 100}%
                      </p>
                    </div>
                    <span className="text-sm font-medium underline">
                      Manage clinic
                    </span>
                  </a>
                </li>
              ))}
          </ul>
          {clinics.hasNextPage && (
            <Button
              className="mt-6"
              disabled={clinics.isFetching}
              onClick={() => void clinics.fetchNextPage()}
            >
              Load more clinics
            </Button>
          )}
        </>
      )}
    </section>
  )
}
