import { formatBookingTime } from './display'
import type { BookingSlot } from './fixtures'

export function BookingSlotCell({
  slot,
  selected,
  onSelect,
}: {
  slot: BookingSlot
  selected: boolean
  onSelect: () => void
}) {
  return (
    <button
      type="button"
      disabled={slot.availability !== 'available'}
      aria-pressed={selected}
      onClick={onSelect}
      className={`rounded-xl border p-4 text-left focus-visible:outline-2 focus-visible:outline-offset-2 disabled:bg-slate-100 disabled:text-slate-400 ${selected ? 'border-teal-700 bg-teal-50 ring-1 ring-teal-700' : 'bg-white enabled:hover:border-teal-600'}`}
    >
      <span className="block font-semibold">
        {formatBookingTime(slot.starts_at)}–{formatBookingTime(slot.ends_at)}
      </span>
      <span className="mt-1 block text-sm">{slot.doctor_name}</span>
      <span className="mt-2 block text-xs">
        {slot.availability === 'available' ? 'Available' : 'Unavailable'}
      </span>
    </button>
  )
}
