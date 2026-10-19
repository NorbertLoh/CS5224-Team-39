import { useState } from 'react'
import { useInfiniteQuery, useQuery } from '@tanstack/react-query'
import { useSchedulingIdentity } from '../scheduling/useSchedulingIdentity'
import {
  fulfilmentError,
  listOrders,
  orderSnapshot,
  ownsOrder,
  trackingOrder,
} from './api'
import type { OrderSnapshot } from './api'
import type { PreviewContext } from './model'
import { TrackingOrderList } from './TrackingOrderList'
import { TrackingOrderDetails } from './TrackingOrderDetails'
import { LiveMedicineReadiness } from './LiveMedicineReadiness'
import { LiveMedicationCheckout } from './LiveMedicationCheckout'
import { CreateMedicationOrder } from './CreateMedicationOrder'

type Props = { role: 'patient' } | { role: 'clinic_admin'; tenantId: string }
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

export function LiveOrders(props: Props) {
  const identity = useSchedulingIdentity()
  if (identity.isError)
    return (
      <p role="alert" className="p-6">
        Could not verify order access. Refresh your session and try again.
      </p>
    )
  if (!identity.data || !identity.token)
    return (
      <p role="status" className="p-6">
        Checking order access...
      </p>
    )
  const context: PreviewContext =
    props.role === 'patient'
      ? { role: 'patient', patientId: identity.data.subject_id }
      : { role: 'clinic_admin', tenantId: props.tenantId }
  return (
    <OrderWorkspace
      key={`${identity.token}:${props.role}:${props.role === 'clinic_admin' ? props.tenantId : ''}`}
      context={context}
      token={identity.token}
    />
  )
}

function OrderWorkspace({
  context,
  token,
}: {
  context: PreviewContext
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
  return (
    <main className="mx-auto max-w-5xl space-y-6 px-4 py-8 sm:px-6">
      <a
        className="text-sm underline"
        href={patient ? '/patient' : '/clinic-admin'}
      >
        {patient ? 'Back to patient dashboard' : 'Back to your clinics'}
      </a>
      <h1 className="text-3xl font-semibold">
        {patient
          ? 'Medication orders and delivery'
          : 'Medicine readiness and delivery'}
      </h1>
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
      <button
        className="rounded-lg border px-4 py-2"
        disabled={list.isFetching || detail.isFetching}
        onClick={() => {
          void list.refetch()
          if (validId) void detail.refetch()
        }}
      >
        Refresh orders and status
      </button>
      {list.isPending ? (
        <p role="status">Loading medication orders...</p>
      ) : list.isError ? (
        <p role="alert">{fulfilmentError(list.error)}</p>
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
            {selectedId && !validId && (
              <p role="alert">
                Invalid order reference. Select an order from the list.
              </p>
            )}
            {validId &&
              (detail.isPending ? (
                <p role="status">Loading order details...</p>
              ) : detail.isError ? (
                <p role="alert">{fulfilmentError(detail.error)}</p>
              ) : (
                snapshot && (
                  <>
                    <TrackingOrderDetails
                      key={snapshot.order.order_id}
                      order={trackingOrder(snapshot.order, snapshot.delivery)}
                      context={context}
                      onReady={() => undefined}
                      preview={false}
                      readiness={
                        patient ? (
                          <></>
                        ) : (
                          <LiveMedicineReadiness
                            order={snapshot.order}
                            context={context}
                            onRefresh={() => {
                              void refresh().catch(() => undefined)
                            }}
                          />
                        )
                      }
                    />
                    {patient && (
                      <LiveMedicationCheckout
                        key={snapshot.order.order_id}
                        snapshot={snapshot}
                        subject={context.patientId}
                        refresh={refresh}
                      />
                    )}
                  </>
                )
              ))}
            {!selectedId && rows.length > 0 && (
              <p className="text-sm">
                Select an order to view its current status.
              </p>
            )}
          </div>
        </div>
      )}
    </main>
  )
}
