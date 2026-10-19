import { useState } from 'react'
import { canMarkReady } from './model'
import type { PreviewContext, TrackingOrder } from './model'

export function MedicineReadiness({
  order,
  context,
  onReady,
}: {
  order: TrackingOrder
  context: PreviewContext
  onReady: () => void
}) {
  const [simulateError, setSimulateError] = useState(false)
  const [feedback, setFeedback] = useState<'error' | 'success' | null>(null)
  if (context.role !== 'clinic_admin') return null
  const allowed = canMarkReady(order, context)
  return (
    <section
      className="space-y-3 rounded-xl border p-4"
      aria-labelledby="medicine-readiness-heading"
    >
      <h3 id="medicine-readiness-heading" className="font-semibold">
        Medicine preparation
      </h3>
      <p className="text-sm">
        Confirm that this order’s medicine has been prepared. Payment and
        courier status are checked separately.
      </p>
      {!allowed && (
        <p role="status" className="text-sm">
          Readiness cannot be changed for this order.
        </p>
      )}
      <button
        className="rounded-lg bg-slate-900 px-4 py-2 text-sm text-white disabled:opacity-50"
        disabled={!allowed || order.medicine_status === 'ready'}
        onClick={() => {
          if (simulateError) {
            setFeedback('error')
            return
          }
          onReady()
          setFeedback('success')
        }}
      >
        {order.medicine_status === 'ready'
          ? 'Medicine already ready'
          : feedback === 'error'
            ? 'Retry demo readiness'
            : 'Mark medicine ready (demo)'}
      </button>
      {feedback === 'error' && (
        <p role="alert" className="text-sm text-red-700">
          Could not confirm readiness. Medicine status has not changed. Retry
          the same action after clearing the simulated error.
        </p>
      )}
      {feedback === 'success' && (
        <p role="status" className="text-sm">
          Medicine marked ready. Payment and delivery status are unchanged.
        </p>
      )}
      <label className="block text-sm">
        <input
          type="checkbox"
          checked={simulateError}
          onChange={(event) => setSimulateError(event.target.checked)}
        />{' '}
        Simulate readiness action error
      </label>
    </section>
  )
}
