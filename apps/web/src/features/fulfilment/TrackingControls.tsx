import { examples } from './fixtures'
import type { Example } from './fixtures'

export function TrackingControls({
  example,
  onExampleChange,
  onRefresh,
  refreshingExample,
}: {
  example: Example
  onExampleChange: (value: Example) => void
  onRefresh: () => void
  refreshingExample: boolean
}) {
  return (
    <aside className="space-y-3 rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm">
      <p className="font-semibold">
        Readiness and tracking preview · synthetic data
      </p>
      <p>
        No live order is changed and no courier is booked. Each example is an
        independent historical snapshot; switching examples resets readiness
        changes.
      </p>
      <label className="block font-medium">
        Tracking example
        <select
          className="mt-1 block w-full rounded border bg-white p-2"
          value={example}
          onChange={(event) => onExampleChange(event.target.value as Example)}
        >
          {Object.entries(examples).map(([key, label]) => (
            <option key={key} value={key}>
              {label}
            </option>
          ))}
        </select>
      </label>
      <button
        className="rounded-lg border bg-white px-4 py-2"
        disabled={refreshingExample}
        onClick={onRefresh}
      >
        Refresh demo status
      </button>
      <p>
        Refresh checks the current example. It does not advance delivery or
        create another attempt.
      </p>
    </aside>
  )
}
