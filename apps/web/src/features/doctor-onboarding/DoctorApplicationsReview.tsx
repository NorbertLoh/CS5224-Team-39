import { readSession } from '@/auth/session'
import { ErrorState } from '@/components/ErrorState'
import { LoadingState } from '@/components/LoadingState'
import { Button } from '@/components/ui/button'

import { useInfiniteQuery, useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { CountTabs } from '@/components/CountTabs'
import { ListFilters } from '@/components/ListFilters'
import { emptyFilters } from '@/lib/list-filters'
import type { DoctorApplication } from './api'
import { DoctorApplicationReviewCard } from './DoctorApplicationReviewCard'
import { applicationCounts, listApplications } from './api'

const statuses: { value: DoctorApplication['status']; label: string }[] = [
  { value: 'pending', label: 'Pending review' },
  { value: 'approved', label: 'Approved' },
  { value: 'rejected', label: 'Rejected' },
  { value: 'revoked', label: 'Resubmission required' },
]

export function DoctorApplicationsReview() {
  const [status, setStatus] = useState<DoctorApplication['status']>('pending')
  const [filters, setFilters] = useState(emptyFilters)
  const counts = useQuery({
    queryKey: [
      'doctor-applications',
      'counts',
      readSession()?.accessToken,
      filters,
    ],
    queryFn: ({ signal }) => applicationCounts(signal, filters),
    refetchInterval: 30000,
  })
  const applications = useInfiniteQuery({
    queryKey: [
      'doctor-applications',
      readSession()?.accessToken,
      status,
      filters,
    ],
    initialPageParam: null as string | null,
    queryFn: ({ pageParam, signal }) =>
      listApplications(status, pageParam, signal, filters),
    getNextPageParam: (page) =>
      page.length === 25 ? page.at(-1)?.subject_id : undefined,
    refetchInterval: 30000,
  })
  return (
    <main className="mx-auto max-w-5xl px-6 py-10">
      <a href="/platform-admin/clinics" className="text-sm underline">
        Manage clinics
      </a>
      <h1 className="mt-4 text-3xl font-semibold">Doctor applications</h1>
      <p className="mt-3 text-slate-600">
        Review the licence and supporting evidence before granting doctor
        eligibility. Clinic access still requires an active membership.
      </p>
      <ListFilters
        value={filters}
        onApply={setFilters}
        dateLabel="Submitted"
        placeholder="Doctor name, licence, authority, specialty or ID"
      />
      <p className="mt-4 text-sm text-slate-500" aria-live="polite">
        Total applications:{' '}
        <span className="font-semibold text-slate-900">
          {counts.data?.total ?? '—'}
        </span>
      </p>
      {counts.isError && (
        <ErrorState
          message="Could not refresh application totals."
          onRetry={() => void counts.refetch()}
        />
      )}
      <CountTabs
        value={status}
        onChange={(value) => setStatus(value as DoctorApplication['status'])}
        items={statuses}
        counts={counts.data}
        label="Application status"
      >
        {applications.isPending ? (
          <LoadingState message="Loading applications..." />
        ) : applications.isError ? (
          <ErrorState
            message="Could not load applications."
            onRetry={() => void applications.refetch()}
          />
        ) : (
          <>
            {!applications.data.pages.some((page) => page.length) && (
              <p className="mt-6 text-slate-600">
                No applications with this status.
              </p>
            )}
            <div className="mt-6 grid gap-5">
              {applications.data.pages.flat().map((application) => (
                <DoctorApplicationReviewCard
                  key={`${application.subject_id}:${application.revision}:${application.status}`}
                  application={application}
                />
              ))}
            </div>
            {applications.hasNextPage && (
              <Button
                className="mt-5"
                disabled={applications.isFetching}
                onClick={() => void applications.fetchNextPage()}
              >
                Load more applications
              </Button>
            )}
          </>
        )}
      </CountTabs>
    </main>
  )
}
