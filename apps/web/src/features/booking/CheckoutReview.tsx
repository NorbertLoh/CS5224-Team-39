import { useEffect, useRef, useState } from 'react'
import { consultationPrice } from '../../lib/money'
import {
  formatBookingDate,
  formatBookingTime,
  holdSeconds,
  singaporeDate,
} from './fixtures'
import type { BookingHold } from './fixtures'

export function CheckoutReview({
  hold,
  clinicName,
  onBack,
}: {
  hold: BookingHold
  clinicName: string
  onBack: () => void
}) {
  const [now, setNow] = useState(Date.now)
  const heading = useRef<HTMLHeadingElement>(null)
  useEffect(() => {
    heading.current?.focus()
    const timer = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(timer)
  }, [])
  const seconds = holdSeconds(hold, now)
  const slot = hold.slot
  return (
    <section
      className="mx-auto max-w-xl space-y-5 rounded-2xl border bg-white p-6"
      aria-labelledby="checkout-heading"
    >
      <h2
        ref={heading}
        tabIndex={-1}
        id="checkout-heading"
        className="text-2xl font-semibold"
      >
        Checkout
      </h2>
      <dl className="space-y-4">
        {[
          ['Clinic', clinicName],
          ['Doctor', slot.doctor_name],
          [
            'Date',
            formatBookingDate(singaporeDate(Date.parse(slot.starts_at))),
          ],
          [
            'Time (SGT)',
            `${formatBookingTime(slot.starts_at)}–${formatBookingTime(slot.ends_at)}`,
          ],
          [
            'Consultation fee',
            consultationPrice(
              slot.consultation_price.amount_minor,
              slot.consultation_price.currency,
            ),
          ],
        ].map(([label, value]) => (
          <div key={label} className="flex flex-wrap justify-between gap-2">
            <dt className="text-slate-500">{label}</dt>
            <dd className="font-medium">{value}</dd>
          </div>
        ))}
      </dl>
      <p
        role="status"
        className="rounded-lg bg-amber-50 p-3 text-sm text-amber-900"
      >
        {seconds
          ? `Demo hold expires in ${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}.`
          : 'This demo hold has expired. Choose a time again.'}
      </p>
      <p className="text-sm text-slate-600">
        Checkout preview. No appointment has been reserved and no payment will
        be taken. Payment checkout will be connected when billing is ready.
      </p>
      <button
        type="button"
        onClick={onBack}
        className="rounded-lg border px-4 py-3 font-medium"
      >
        {seconds ? 'Change time' : 'Choose another time'}
      </button>
    </section>
  )
}
