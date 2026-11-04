import { ErrorState } from '@/components/ErrorState'
import { LoadingState } from '@/components/LoadingState'
import { Button } from '@/components/ui/button'
import type { Order } from '@/features/fulfilment/api'
import { trackingOrder } from '@/features/fulfilment/domain/tracking'
import type { Prescription } from '@/features/fulfilment/api/pricing'
import { request } from '@/features/fulfilment/api/pricing'
import { orderLabels, trackingTime } from '@/features/fulfilment/domain/model'
import { orderAppearance } from '@/features/fulfilment/domain/orderAppearance'
import { PrescriptionPriceCard } from '@/features/fulfilment/pricing/PrescriptionPriceCard'
import { PatientAccordionItem } from '@/features/patient/components/PatientAccordionItem'
import { useInfiniteQuery } from '@tanstack/react-query'
import type { ReactNode } from 'react'

export function ClinicMedicineCards({
  tenantId,
  token,
  orders,
  selectedId,
  onSelect,
  orderDetails,
}: {
  tenantId: string
  token: string
  orders: Order[]
  selectedId: string | null
  onSelect: (id: string | null) => void
  orderDetails: ReactNode
}) {
  const query = useInfiniteQuery({
    queryKey: ['clinic-prescription-pricing', token, tenantId],
    initialPageParam: null as string | null,
    queryFn: async ({ pageParam, signal }) =>
      (
        await request(
          `/clinical-records/clinics/${encodeURIComponent(tenantId)}/prescription-pricing${pageParam ? '?cursor=' + encodeURIComponent(pageParam) : ''}`,
          { signal },
        )
      ).json() as Promise<{
        items: Prescription[]
        next_cursor: string | null
      }>,
    getNextPageParam: (page) => page.next_cursor ?? undefined,
    retry: false,
    gcTime: 0,
    refetchOnWindowFocus: false,
  })
  const rows = query.data?.pages.flatMap((page) => page.items) ?? []
  const orderPrescriptions = new Set(
    orders.map((order) => order.prescription_id),
  )
  const cards = [
    ...orders.map((order) => ({
      id: order.prescription_id,
      created: order.created_at,
      order,
      prescription: null,
    })),
    ...rows
      .filter((row) => !orderPrescriptions.has(row.prescription_id))
      .map((prescription) => ({
        id: prescription.prescription_id,
        created: prescription.created_at,
        order: null,
        prescription,
      })),
  ].sort(
    (a, b) =>
      Date.parse(b.created) - Date.parse(a.created) || b.id.localeCompare(a.id),
  )
  return (
    <div className="space-y-4">
      {query.isPending && (
        <LoadingState message="Loading medicine prescriptions..." />
      )}
      {cards.map(({ id, order, prescription }) => {
        const appearance = order ? orderAppearance(trackingOrder(order)) : null
        return order ? (
          <div
            key={id}
            className={`rounded-2xl border-2 bg-white px-5 ${appearance?.border}`}
          >
            <PatientAccordionItem
              title={
                <span className="flex flex-wrap items-center gap-2">
                  <span>Order {order.order_id.slice(-8)}</span>
                  <span className={`text-xs ${appearance?.text}`}>
                    {appearance?.label}
                  </span>
                </span>
              }
              summary={
                <>
                  <span className="block">
                    {order.items.map((item) => item.display_name).join(', ')}
                  </span>
                  <span className="block">
                    {trackingTime(order.created_at)} ·{' '}
                    {orderLabels[order.status]} ·{' '}
                    {order.medicine_status === 'ready'
                      ? 'Medicine ready'
                      : 'Medicine not ready'}
                  </span>
                </>
              }
              open={selectedId === order.order_id}
              onToggle={() =>
                onSelect(selectedId === order.order_id ? null : order.order_id)
              }
            >
              {selectedId === order.order_id && orderDetails}
            </PatientAccordionItem>
          </div>
        ) : (
          prescription && (
            <PrescriptionPriceCard
              key={id}
              prescription={prescription}
              tenantId={tenantId}
              token={token}
            />
          )
        )
      })}
      {!cards.length && !query.isPending && !query.isError && (
        <p className="text-sm text-slate-600">
          Issued prescriptions and medicine orders will appear here.
        </p>
      )}
      {query.isError && (
        <ErrorState
          message="Could not load prescriptions. Check your clinic access and retry."
          onRetry={() => void query.refetch()}
        />
      )}
      <div className="flex flex-wrap gap-3">
        <Button
          variant="outline"
          type="button"
          disabled={query.isFetching}
          onClick={() => void query.refetch()}
        >
          Refresh medicine prescriptions
        </Button>
        {query.hasNextPage && (
          <Button
            variant="outline"
            type="button"
            disabled={query.isFetching}
            onClick={() => void query.fetchNextPage()}
          >
            Load older prescriptions
          </Button>
        )}
      </div>
    </div>
  )
}
