import { formatDate } from './fixtures'
import type { AppointmentRole } from './fixtures'

export function AppointmentFilters({
  role,
  contexts,
  contextId,
  dates,
  date,
  onContextChange,
  onDateChange,
}: {
  role: AppointmentRole
  contexts: { id: string; name: string }[]
  contextId: string
  dates: string[]
  date: string
  onContextChange: (id: string) => void
  onDateChange: (date: string) => void
}) {
  return (
    <div className="flex flex-wrap gap-4">
      <label className="flex flex-col gap-1 text-sm font-medium">
        {role === 'clinic_admin' ? 'Demo clinic' : `Demo ${role}`}
        <select
          className="rounded border bg-white px-3 py-2"
          value={contextId}
          onChange={(event) => onContextChange(event.target.value)}
        >
          {contexts.map((context) => (
            <option key={context.id} value={context.id}>
              {context.name}
            </option>
          ))}
        </select>
      </label>
      <label className="flex flex-col gap-1 text-sm font-medium">
        Date
        <select
          className="rounded border bg-white px-3 py-2"
          value={date}
          onChange={(event) => onDateChange(event.target.value)}
        >
          {dates.map((item) => (
            <option key={item} value={item}>
              {formatDate(item)}
            </option>
          ))}
        </select>
      </label>
    </div>
  )
}
