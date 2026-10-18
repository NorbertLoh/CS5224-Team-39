import { useState } from 'react'
import { useInfiniteQuery, useQuery } from '@tanstack/react-query'
import { readClinic } from '../clinic-profile/logo-api'
import { readSession } from '../../auth/session'
import { listPayments, paymentTotals } from './api'
import { purposeLabels, statusLabels } from './model'
import { CommissionSummary } from './CommissionSummary'
import { PaymentHistory } from './PaymentHistory'
import { PaymentFilter } from './PaymentFilter'
import { ClinicPaymentNavigation } from './ClinicPaymentNavigation'
import { ErrorState } from '../../components/ErrorState'
import { LoadingState } from '../../components/LoadingState'
import { billingError } from '../checkout/live'

export function ClinicPayments({ tenantId }: { tenantId: string }) {
  const [purpose, setPurpose] = useState('all')
  const [status, setStatus] = useState('all')
  const token = readSession()?.accessToken
  const clinic = useQuery({
    queryKey: ['billing', 'clinic', token, tenantId],
    queryFn: () => readClinic(tenantId),
    retry: false,
  })
  const history = useInfiniteQuery({
    queryKey: ['billing', 'history', token, tenantId, purpose, status],
    initialPageParam: null as string | null,
    queryFn: ({ pageParam, signal }) =>
      listPayments(tenantId, purpose, status, pageParam, signal),
    getNextPageParam: (page) => page.next_cursor ?? undefined,
    retry: false,
    refetchOnWindowFocus: true,
  })
  const totals = useQuery({
    queryKey: ['billing', 'totals', token, tenantId, purpose],
    queryFn: ({ signal }) => paymentTotals(tenantId, purpose, signal),
    retry: false,
    refetchOnWindowFocus: true,
  })
  const refresh = () => {
    void history.refetch()
    void totals.refetch()
  }
  const rows = history.data?.pages.flatMap((page) => page.items) ?? []
  return (
    <main className="mx-auto max-w-6xl space-y-8 px-4 py-8 sm:px-6">
      <ClinicPaymentNavigation tenantId={tenantId} />
      <p className="text-sm text-slate-600">
        {clinic.data?.name ?? `Clinic ${tenantId}`}
      </p>
      <h1 className="text-3xl font-semibold">Payments and commission</h1>
      <button className="rounded border px-4 py-2" onClick={refresh}>
        Refresh payments
      </button>
      <PaymentFilter
        label="Payment purpose"
        value={purpose}
        onChange={setPurpose}
        options={{ all: 'All purposes', ...purposeLabels }}
      />
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
      <section className="space-y-4" aria-labelledby="payment-history-heading">
        <h2 id="payment-history-heading" className="text-xl font-semibold">
          Payment history
        </h2>
        <PaymentFilter
          label="History status"
          value={status}
          onChange={setStatus}
          options={{ all: 'All statuses', ...statusLabels }}
        />
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
            className="rounded border px-4 py-2"
            disabled={history.isFetching}
            onClick={() => void history.fetchNextPage()}
          >
            Load more payments
          </button>
        )}
      </section>
    </main>
  )
}
