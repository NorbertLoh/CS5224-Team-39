import { consultationPrice } from '../../lib/money'
import { formatBookingDate, formatBookingTime, singaporeDate } from './fixtures'
import type { BookingSlot } from './fixtures'

export function SlotPicker({
  slots,
  dates,
  date,
  selectedId,
  onDate,
  onSelect,
  onCheckout,
}: {
  slots: BookingSlot[]
  dates: string[]
  date: string
  selectedId: string | null
  onDate: (date: string) => void
  onSelect: (id: string) => void
  onCheckout: () => void
}) {
  const daySlots = slots.filter(
    (slot) => singaporeDate(Date.parse(slot.starts_at)) === date,
  )
  const selected = daySlots.find(
    (slot) => slot.slot_id === selectedId && slot.availability === 'available',
  )
  return (
    <section className="space-y-5" aria-labelledby="slot-heading">
      <h2 id="slot-heading" className="text-2xl font-semibold">
        Choose a time
      </h2>
      <label className="flex max-w-sm flex-col gap-2 text-sm font-medium">
        Date
        <select
          className="rounded-lg border bg-white px-3 py-3"
          value={date}
          onChange={(event) => onDate(event.target.value)}
        >
          {dates.map((item) => (
            <option key={item} value={item}>
              {formatBookingDate(item)}
            </option>
          ))}
        </select>
      </label>
      <p className="text-sm text-slate-600">
        30-minute consultations · Singapore time (SGT)
      </p>
      {!daySlots.some((slot) => slot.availability === 'available') && (
        <p role="status">
          No available times on this date. Choose another date.
        </p>
      )}
      <div
        className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4"
        aria-label="Consultation time slots"
      >
        {daySlots.map((slot) => (
          <button
            key={slot.slot_id}
            type="button"
            disabled={slot.availability !== 'available'}
            aria-pressed={selectedId === slot.slot_id}
            onClick={() => onSelect(slot.slot_id)}
            className={`rounded-xl border p-4 text-left focus-visible:outline-2 focus-visible:outline-offset-2 disabled:bg-slate-100 disabled:text-slate-400 ${selectedId === slot.slot_id ? 'border-teal-700 bg-teal-50 ring-1 ring-teal-700' : 'bg-white enabled:hover:border-teal-600'}`}
          >
            <span className="block font-semibold">
              {formatBookingTime(slot.starts_at)}–
              {formatBookingTime(slot.ends_at)}
            </span>
            <span className="mt-1 block text-sm">{slot.doctor_name}</span>
            <span className="mt-2 block text-xs">
              {slot.availability === 'available' ? 'Available' : 'Unavailable'}
            </span>
          </button>
        ))}
      </div>
      <div className="sticky bottom-0 flex flex-wrap items-center justify-between gap-4 rounded-xl border bg-white p-4 shadow-sm">
        <p role="status" className="text-sm">
          {selected
            ? `${formatBookingDate(date)}, ${formatBookingTime(selected.starts_at)} · ${selected.doctor_name} · ${consultationPrice(selected.consultation_price.amount_minor, selected.consultation_price.currency)}`
            : 'Select an available time to continue.'}
        </p>
        <button
          type="button"
          disabled={!selected}
          onClick={onCheckout}
          className="rounded-lg bg-teal-700 px-5 py-3 font-medium text-white disabled:opacity-40"
        >
          Continue to checkout
        </button>
      </div>
    </section>
  )
}
