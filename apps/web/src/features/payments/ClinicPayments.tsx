import { readSession } from '@/auth/session'
import { ErrorState } from '@/components/ErrorState'
import { LoadingState } from '@/components/LoadingState'
import { CountTabs } from '@/components/CountTabs'
import { ListFilters } from '@/components/ListFilters'
import { billingError } from '@/features/checkout/live'
import {
  listPayments,
  paymentCounts,
  paymentTotals,
} from '@/features/payments/api'
import { CommissionSummary } from '@/features/payments/CommissionSummary'
import { purposeLabels, statusLabels } from '@/features/payments/model'
import { PaymentHistory } from '@/features/payments/PaymentHistory'
import { emptyFilters } from '@/lib/list-filters'
import { useInfiniteQuery, useQuery } from '@tanstack/react-query'
import { useState } from 'react'

export function ClinicPayments({ tenantId }: { tenantId: string }) {
  const [purpose, setPurpose] = useState('all')
  const [status, setStatus] = useState('all')
  const [filters, setFilters] = useState(emptyFilters)
  const token = readSession()?.accessToken
  const history = useInfiniteQuery({
    queryKey: ['billing', 'history', token, tenantId, purpose, status, filters],
    initialPageParam: null as string | null,
    queryFn: ({ pageParam, signal }) =>
      listPayments(tenantId, purpose, status, pageParam, signal, filters),
    getNextPageParam: (page) => page.next_cursor ?? undefined,
    retry: false,
    refetchInterval: 5000,
  })
  const totals = useQuery({
    queryKey: ['billing', 'totals', token, tenantId, purpose, filters],
    queryFn: ({ signal }) => paymentTotals(tenantId, purpose, signal, filters),
    retry: false,
    refetchInterval: 5000,
  })
  const counts = useQuery({
    queryKey: ['billing', 'counts', token, tenantId, purpose, status, filters],
    queryFn: ({ signal }) =>
      paymentCounts(tenantId, purpose, status, filters, signal),
    retry: false,
    refetchInterval: 5000,
  })
  const refresh = () => {
    void history.refetch()
    void totals.refetch()
    void counts.refetch()
  }
  const rows = history.data?.pages.flatMap((page) => page.items) ?? []
  return (
    <main className="mx-auto max-w-6xl space-y-6 px-4 py-8 sm:px-6">
      <h1 className="text-3xl font-semibold">Payments and commission</h1>
      <ListFilters
        value={filters}
        onApply={setFilters}
        dateLabel="Payment created"
        placeholder="Payment, patient, appointment, order or quote ID"
      />
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-slate-600" aria-live="polite">
          {counts.data?.filtered_total ?? '—'} matching payments
        </p>
        <button className="rounded border px-4 py-2" onClick={refresh}>
          Refresh payments
        </button>
      </div>
      {counts.isError && (
        <ErrorState
          message="Could not refresh payment counts."
          onRetry={refresh}
        />
      )}
      <CountTabs
        value={purpose}
        onChange={setPurpose}
        label="Payment purpose"
        items={[
          { value: 'all', label: 'All purposes' },
          ...Object.entries(purposeLabels).map(([value, label]) => ({
            value,
            label,
          })),
        ]}
        counts={counts.data?.purpose}
      >
        <p className="mb-4 text-sm text-slate-500">
          Commission totals cover successful payments matching the selected
          purpose, search and dates. The history status filter applies to the
          list below.
        </p>
        {totals.isError ? (
          <ErrorState message={billingError} onRetry={refresh} />
        ) : totals.data ? (
          <CommissionSummary
            totals={{
              count: totals.data.payment_count,
              amount: totals.data.amount.amount_minor,
              commission: totals.data.commission_amount.amount_minor,
              clinic: totals.data.clinic_amount.amount_minor,
            }}
          />
        ) : (
          <LoadingState message="Loading commission totals..." />
        )}
        <section
          className="mt-8 space-y-4"
          aria-labelledby="payment-history-heading"
        >
          <h2 id="payment-history-heading" className="text-xl font-semibold">
            Payment history
          </h2>
          <CountTabs
            value={status}
            onChange={setStatus}
            label="Payment history status"
            items={[
              { value: 'all', label: 'All statuses' },
              ...Object.entries(statusLabels).map(([value, label]) => ({
                value,
                label,
              })),
            ]}
            counts={counts.data?.status}
          >
            {history.isError ? (
              <ErrorState message={billingError} onRetry={refresh} />
            ) : history.isPending ? (
              <LoadingState message="Loading payments..." />
            ) : (
              <PaymentHistory
                payments={rows.filter((row) => row.tenant_id === tenantId)}
              />
            )}
            {history.hasNextPage && (
              <button
                className="mt-4 rounded border px-4 py-2"
                disabled={history.isFetching}
                onClick={() => void history.fetchNextPage()}
              >
                Load more payments
              </button>
            )}
          </CountTabs>
        </section>
      </CountTabs>
    </main>
  )
}
