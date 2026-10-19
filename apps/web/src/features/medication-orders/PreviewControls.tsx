import { singaporeTime } from './model'
import type { Outcome } from './model'

const paymentOutcomes: Record<Outcome, string> = {
  pending: 'Payment still pending',
  cancelled: 'Checkout cancelled, status still pending',
  unknown: 'Status unavailable',
  failed: 'Payment failure verified',
  confirming: 'Payment succeeded, order update pending',
  paid: 'Payment and order confirmed',
  refund_required: 'Late payment requires manual refund review',
}

export function PreviewControls({
  now,
  hasQuote,
  unavailable,
  outcome,
  onUnavailableChange,
  onOutcomeChange,
  onExpire,
}: {
  now: number
  hasQuote: boolean
  unavailable: boolean
  outcome: Outcome
  onUnavailableChange: (value: boolean) => void
  onOutcomeChange: (value: Outcome) => void
  onExpire: () => void
}) {
  return (
    <details className="rounded-xl border p-4 text-sm">
      <summary className="cursor-pointer font-medium">Preview controls</summary>
      <div className="mt-3 space-y-3">
        <p>
          Demo clock: {singaporeTime(now)}. It advances while this page is open.
        </p>
        <label className="block">
          <input
            type="checkbox"
            checked={unavailable}
            onChange={(event) => onUnavailableChange(event.target.checked)}
          />{' '}
          Simulate unavailable delivery quote
        </label>
        <label className="block">
          Next payment status check
          <select
            className="mt-1 block w-full rounded border bg-white p-2"
            value={outcome}
            onChange={(event) => onOutcomeChange(event.target.value as Outcome)}
          >
            {Object.entries(paymentOutcomes).map(([key, label]) => (
              <option key={key} value={key}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <button
          className="rounded border px-4 py-2"
          disabled={!hasQuote}
          onClick={onExpire}
        >
          Advance to quote deadline
        </button>
        <p>
          Changing a preview control applies only when you request a quote or
          check payment status.
        </p>
      </div>
    </details>
  )
}
