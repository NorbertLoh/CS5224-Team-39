import { useState } from 'react'
import { useInfiniteQuery, useQuery } from '@tanstack/react-query'
import {
  fulfilmentError,
  listOrders,
  orderSnapshot,
  ownsOrder,
  trackingOrder,
} from './api'
import type { OrderSnapshot } from './api'
import type { OrderContext } from './model'
import { TrackingOrderList } from './TrackingOrderList'
import { CreateMedicationOrder } from './CreateMedicationOrder'
import { OrderDetailsPanel } from './OrderDetailsPanel'
import { PatientOrderAccordion } from './PatientOrderAccordion'

const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

export function OrderWorkspace({
  context,
  token,
}: {
  context: OrderContext
  token: string
}) {
  const patient = context.role === 'patient'
  const params = new URLSearchParams(window.location.search)
  const supplied = params.get('order_id')
  const prescriptionId = params.get('prescription_id')
  const [selectedId, setSelectedId] = useState<string | null>(
    () =>
      supplied ??
      (patient && !prescriptionId
        ? sessionStorage.getItem(
            `telelink.medication-return.${context.patientId}`,
          )
        : null),
  )
  const validId = selectedId !== null && uuid.test(selectedId)
  const directReview = patient && supplied !== null && validId
  const list = useInfiniteQuery({
    queryKey: ['fulfilment', 'orders', token, context],
    initialPageParam: null as string | null,
    queryFn: ({ pageParam, signal }) =>
      listOrders(
        context.role === 'clinic_admin' ? context.tenantId : undefined,
        pageParam,
        signal,
      ),
    getNextPageParam: (page) => page.next_cursor ?? undefined,
    retry: false,
    gcTime: 0,
    refetchOnWindowFocus: true,
    refetchInterval: 10000,
  })
  const detail = useQuery({
    queryKey: ['fulfilment', 'order', token, context, selectedId],
    queryFn: ({ signal }) => orderSnapshot(selectedId!, context, signal),
    enabled: validId,
    retry: false,
    gcTime: 0,
    refetchOnWindowFocus: true,
    refetchInterval: 5000,
  })
  const rows = list.isError
    ? []
    : (list.data?.pages
        .flatMap((page) => page.items)
        .filter((order) => ownsOrder(order, context)) ?? [])
  const snapshot = detail.isError ? undefined : detail.data
  async function refresh(): Promise<OrderSnapshot> {
    const result = await detail.refetch()
    void list.refetch()
    if (result.isError || !result.data) throw new Error('Order unavailable.')
    return result.data
  }
  const visibleRows =
    patient &&
    snapshot &&
    !rows.some((order) => order.order_id === snapshot.order.order_id)
      ? [snapshot.order, ...rows]
      : rows
  const orderDetails =
    selectedId && !validId ? (
      <p role="alert">
        Invalid order reference. Select an order from the list.
      </p>
    ) : validId ? (
      detail.isPending ? (
        <p role="status">Loading order details...</p>
      ) : detail.isError ? (
        <p role="alert">{fulfilmentError(detail.error)}</p>
      ) : (
        snapshot && (
          <OrderDetailsPanel
            snapshot={snapshot}
            context={context}
            refresh={refresh}
          />
        )
      )
    ) : null
  const refreshButton = (
    <button
      className="rounded border px-4 py-2 text-sm"
      disabled={list.isFetching || detail.isFetching}
      onClick={() => {
        void list.refetch()
        if (validId) void detail.refetch()
      }}
    >
      Refresh orders and status
    </button>
  )
  return (
    <main
      className={
        patient
          ? 'mx-auto max-w-6xl px-6 py-10'
          : 'mx-auto max-w-5xl space-y-6 px-4 py-8 sm:px-6'
      }
    >
      <section
        className={
          patient
            ? 'mt-6 space-y-4 rounded-xl border bg-white p-5 sm:p-6'
            : 'space-y-6'
        }
        aria-labelledby="orders-page-heading"
      >
        {!patient && (
          <a
            className="text-sm underline"
            href="/clinic-admin"
          >
            Back to your clinics
          </a>
        )}
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h1 id="orders-page-heading" className="text-3xl font-semibold">
              {patient
                ? 'Medication orders and delivery'
                : 'Medicine readiness and delivery'}
            </h1>
            {patient && (
              <p className="mt-1 max-w-2xl text-sm text-slate-600">
                Expand an order to view medicines, payment and delivery details.
                Medication and delivery are paid separately from your
                consultation.
              </p>
            )}
          </div>
          {refreshButton}
        </div>
        {directReview && (
          <a
            className="inline-block text-sm underline"
            href="/patient/medication-orders"
          >
            View all medication orders
          </a>
        )}
        {!patient && (
          <p className="break-all text-sm text-slate-600">
            Clinic {context.tenantId}
          </p>
        )}
        {patient &&
          prescriptionId &&
          (uuid.test(prescriptionId) ? (
            <CreateMedicationOrder
              prescriptionId={prescriptionId}
              subject={context.patientId}
              token={token}
              onCreated={(id) => {
                setSelectedId(id)
                void list.refetch()
              }}
            />
          ) : (
            <p role="alert">Invalid prescription reference.</p>
          ))}
        {list.isPending ? (
          <p role="status">Loading medication orders...</p>
        ) : list.isError ? (
          <p role="alert">{fulfilmentError(list.error)}</p>
        ) : patient ? (
          <>
            <PatientOrderAccordion
              orders={visibleRows}
              selectedId={selectedId}
              onSelect={setSelectedId}
              snapshot={snapshot}
            >
              {orderDetails}
            </PatientOrderAccordion>
            {selectedId &&
              !visibleRows.some((order) => order.order_id === selectedId) &&
              orderDetails}
            {list.hasNextPage && (
              <button
                className="rounded border px-4 py-2"
                disabled={list.isFetchingNextPage}
                onClick={() => void list.fetchNextPage()}
              >
                Load more orders
              </button>
            )}
          </>
        ) : (
          <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
            <div className="space-y-3">
              <TrackingOrderList
                orders={rows.map((order) =>
                  trackingOrder(
                    order,
                    snapshot?.order.order_id === order.order_id
                      ? snapshot.delivery
                      : (order.delivery_snapshot ?? null),
                  ),
                )}
                selectedId={selectedId}
                onSelect={setSelectedId}
              />
              {list.hasNextPage && (
                <button
                  className="rounded border px-4 py-2"
                  disabled={list.isFetchingNextPage}
                  onClick={() => void list.fetchNextPage()}
                >
                  Load more orders
                </button>
              )}
            </div>
            <div className="space-y-5">
              {orderDetails}
              {!selectedId && rows.length > 0 && (
                <p className="text-sm">
                  Select an order to view its current status.
                </p>
              )}
            </div>
          </div>
        )}
      </section>
    </main>
  )
}
