import { ErrorState } from '@/components/ErrorState'
import { LoadingState } from '@/components/LoadingState'
import { Button } from '@/components/ui/button'
import {
  clinicStatuses,
  clinicCounts,
  listAdminClinics,
} from '@/features/platform-clinics/api'
import { useInfiniteQuery, useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { CountTabs } from '@/components/CountTabs'
import { ListFilters } from '@/components/ListFilters'
import { emptyFilters } from '@/lib/list-filters'

export function ClinicList({ token }: { token: string }) {
  const [status, setStatus] = useState('pending_review')
  const [filters, setFilters] = useState(emptyFilters)
  const counts = useQuery({
    queryKey: ['platform-clinics', 'counts', token, filters],
    queryFn: ({ signal }) => clinicCounts(filters, signal),
    refetchInterval: 30000,
  })
  const clinics = useInfiniteQuery({
    queryKey: ['platform-clinics', token, status, filters],
    initialPageParam: null as string | null,
    queryFn: ({ pageParam, signal }) =>
      listAdminClinics(status, pageParam, signal, filters),
    getNextPageParam: (page) => page.next_cursor ?? undefined,
    refetchInterval: 30000,
  })

  return (
    <section className="mt-8" aria-label="Platform clinics">
      <ListFilters
        value={filters}
        onApply={setFilters}
        dateLabel="Registered"
        placeholder="Clinic name, storefront address or clinic ID"
      />
      {counts.isError && (
        <ErrorState
          message="Could not refresh clinic counts."
          onRetry={() => void counts.refetch()}
        />
      )}
      <CountTabs
        value={status}
        onChange={setStatus}
        label="Clinic status"
        items={[
          { value: '', label: 'All' },
          ...Object.entries(clinicStatuses).map(([value, label]) => ({
            value,
            label,
          })),
        ]}
        counts={
          counts.data ? { ...counts.data, '': counts.data.total } : undefined
        }
      >
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
      </CountTabs>
    </section>
  )
}
