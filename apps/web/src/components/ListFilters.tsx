import { Button } from '@/components/ui/button'
import { useState } from 'react'
import { emptyFilters } from '@/lib/list-filters'
import type { ListFilterValues } from '@/lib/list-filters'

export function ListFilters({
  value,
  onApply,
  placeholder,
  dateLabel,
  statuses,
}: {
  value: ListFilterValues
  onApply: (value: ListFilterValues) => void
  placeholder: string
  dateLabel: string
  statuses?: Record<string, string>
}) {
  const [draft, setDraft] = useState(value)
  const [message, setMessage] = useState('')
  return (
    <form
      className="my-5 rounded-xl border bg-slate-50 p-4"
      onSubmit={(event) => {
        event.preventDefault()
        if (draft.from && draft.to && draft.from > draft.to) {
          setMessage('Choose an end date on or after the start date.')
          return
        }
        setMessage('')
        onApply({ ...draft, q: draft.q.trim() })
      }}
    >
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <label className="grid min-w-0 gap-2 text-sm font-medium sm:col-span-2">
          Search
          <input
            type="search"
            maxLength={200}
            value={draft.q}
            placeholder={placeholder}
            onChange={(event) => setDraft({ ...draft, q: event.target.value })}
            className="min-w-0 rounded-lg border bg-white p-2.5 font-normal"
          />
        </label>
        <label className="grid gap-2 text-sm font-medium">
          {dateLabel} from (SGT)
          <input
            type="date"
            value={draft.from}
            onChange={(event) =>
              setDraft({ ...draft, from: event.target.value })
            }
            className="min-w-0 rounded-lg border bg-white p-2.5 font-normal"
          />
        </label>
        <label className="grid gap-2 text-sm font-medium">
          {dateLabel} to (SGT)
          <input
            type="date"
            value={draft.to}
            min={draft.from || undefined}
            onChange={(event) => setDraft({ ...draft, to: event.target.value })}
            className="min-w-0 rounded-lg border bg-white p-2.5 font-normal"
          />
        </label>
        {statuses && (
          <label className="grid gap-2 text-sm font-medium">
            Status
            <select
              value={draft.status}
              onChange={(event) =>
                setDraft({ ...draft, status: event.target.value })
              }
              className="rounded-lg border bg-white p-2.5 font-normal"
            >
              <option value="all">All statuses</option>
              {Object.entries(statuses).map(([key, label]) => (
                <option key={key} value={key}>
                  {label}
                </option>
              ))}
            </select>
          </label>
        )}
      </div>
      <div className="mt-4 flex gap-3">
        <Button type="submit">Apply search &amp; filters</Button>
        <Button
          type="button"
          variant="outline"
          onClick={() => {
            setDraft(emptyFilters)
            setMessage('')
            onApply(emptyFilters)
          }}
        >
          Reset
        </Button>
      </div>
      {message && (
        <p role="alert" className="mt-3 text-sm text-red-700">
          {message}
        </p>
      )}
    </form>
  )
}
