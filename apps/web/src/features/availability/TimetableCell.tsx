import type {
  KeyboardEventHandler,
  MouseEventHandler,
  PointerEventHandler,
} from 'react'
import { slotStart } from './slot-time'
import type { Slot } from './fixtures'
import type { Cell } from './timetable'

type TimetableCellProps = {
  cell: Cell
  date: string
  time: string
  slots: Slot[]
  tenantId: string
  selected: boolean
  onPointerDown: PointerEventHandler<HTMLButtonElement>
  onClick: MouseEventHandler<HTMLButtonElement>
  onKeyDown: KeyboardEventHandler<HTMLButtonElement>
}

function cellAppearance(slots: Slot[], tenantId: string, start: number) {
  const overlaps = slots.filter(
    (slot) =>
      Date.parse(slot.starts_at) < start + 1800000 &&
      Date.parse(slot.ends_at) > start,
  )
  if (overlaps.some((slot) => slot.tenant_id !== tenantId)) {
    return {
      label: 'Other clinic',
      className: 'bg-violet-100 text-violet-900',
      text: 'Other clinic',
    }
  }
  if (overlaps.some((slot) => slot.availability !== 'available')) {
    return {
      label: 'Unavailable',
      className: 'bg-slate-200 text-slate-700',
      text: 'Unavailable',
    }
  }
  if (overlaps.length) {
    return {
      label: 'Available',
      className: 'bg-emerald-100 text-emerald-900',
      text: 'Available',
    }
  }
  if (start <= Date.now()) {
    return { label: 'Past', className: 'bg-slate-50 text-slate-400', text: '' }
  }
  return { label: 'Empty', className: 'bg-white hover:bg-sky-50', text: '' }
}

export function TimetableCell({
  cell,
  date,
  time,
  slots,
  tenantId,
  selected,
  onPointerDown,
  onClick,
  onKeyDown,
}: TimetableCellProps) {
  const appearance = cellAppearance(slots, tenantId, slotStart(date, time))
  const selectedClass = selected
    ? 'ring-2 ring-inset ring-sky-600 brightness-95'
    : ''

  return (
    <td className="border-t border-l p-0">
      <button
        type="button"
        data-day={cell.day}
        data-row={cell.row}
        aria-label={`${date} ${time} SGT, ${appearance.label}`}
        aria-pressed={selected}
        className={`block h-8 w-full touch-none overflow-hidden px-1 text-xs outline-offset-[-3px] focus-visible:outline-2 focus-visible:outline-sky-700 ${appearance.className} ${selectedClass}`}
        onPointerDown={onPointerDown}
        onClick={onClick}
        onKeyDown={onKeyDown}
      >
        {appearance.text}
      </button>
    </td>
  )
}
