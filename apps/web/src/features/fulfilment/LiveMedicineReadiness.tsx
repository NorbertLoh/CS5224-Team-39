import { useMutation } from '@tanstack/react-query'
import { fulfilmentError, readyOrder } from './api'
import type { Order } from './api'
import { canMarkReady } from './model'
import { trackingOrder } from './api'
import type { PreviewContext } from './model'

export function LiveMedicineReadiness({
  order,
  context,
  onRefresh,
}: {
  order: Order
  context: PreviewContext
  onRefresh: () => void
}) {
  const ready = useMutation({
    mutationFn: () => readyOrder(order.order_id),
    retry: false,
    onSuccess: onRefresh,
  })
  if (context.role !== 'clinic_admin') return null
  return (
    <section
      className="space-y-3 rounded-xl border p-4"
      aria-labelledby="live-readiness-heading"
    >
      <h3 id="live-readiness-heading" className="font-semibold">
        Medicine preparation
      </h3>
      <p className="text-sm">
        Mark this order ready once its medicine has been prepared. Payment and
        delivery are checked separately.
      </p>
      <button
        className="rounded-lg bg-slate-900 px-4 py-2 text-sm text-white disabled:opacity-50"
        disabled={
          ready.isPending ||
          order.medicine_status === 'ready' ||
          !canMarkReady(trackingOrder(order), context)
        }
        onClick={() => ready.mutate()}
      >
        {ready.isPending
          ? 'Saving readiness...'
          : order.medicine_status === 'ready'
            ? 'Medicine already ready'
            : 'Mark medicine ready'}
      </button>
      {ready.isError && (
        <p role="alert" className="text-sm text-red-700">
          {fulfilmentError(ready.error)}
        </p>
      )}
      {ready.isSuccess && (
        <p role="status" className="text-sm">
          Readiness saved. Refreshing the current order.
        </p>
      )}
    </section>
  )
}
