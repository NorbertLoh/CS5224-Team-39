import { consultationPrice } from '../../lib/money'
import { formatBookingDate, formatBookingTime, singaporeDate } from './fixtures'
import type { BookingSlot } from './fixtures'

export function BookingSelection({
  selected,
  onCheckout,
}: {
  selected: BookingSlot | undefined
  onCheckout: () => void
}) {
  return (
    <div className="sticky bottom-0 flex flex-wrap items-center justify-between gap-4 rounded-xl border bg-white p-4 shadow-sm">
      <p role="status" className="text-sm">
        {selected
          ? `${formatBookingDate(singaporeDate(Date.parse(selected.starts_at)))}, ${formatBookingTime(selected.starts_at)} · ${selected.doctor_name} · ${consultationPrice(selected.consultation_price.amount_minor, selected.consultation_price.currency)}`
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
  )
}
