import { BookingSlotCell } from './BookingSlotCell'
import { BookingSelection } from './BookingSelection'
import { singaporeDate } from '../scheduling/time'
import type { BookingSlot } from './fixtures'

export function SlotPicker({
  slots,
  date,
  selectedId,
  onSelect,
  onCheckout,
}: {
  slots: BookingSlot[]
  date: string
  selectedId: string | null
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
          <BookingSlotCell
            key={slot.slot_id}
            slot={slot}
            selected={selectedId === slot.slot_id}
            onSelect={() => onSelect(slot.slot_id)}
          />
        ))}
      </div>
      <BookingSelection selected={selected} onCheckout={onCheckout} />
    </section>
  )
}
