import { useState } from 'react'
import type { Clinic, Doctor } from '../clinics/api'
import { ErrorState } from '../../components/ErrorState'
import { bookingDates, createDemoHold, demoSlots } from './fixtures'
import type { BookingHold } from './fixtures'
import { SlotPicker } from './SlotPicker'
import { CheckoutReview } from './CheckoutReview'

export function BookingFlow({
  clinic,
  doctors,
}: {
  clinic: Clinic
  doctors: Doctor[]
}) {
  const [scheduleDay] = useState(Date.now)
  const dates = bookingDates(scheduleDay)
  const slots = demoSlots(clinic, doctors, scheduleDay)
  const [date, setDate] = useState(dates[0])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [hold, setHold] = useState<BookingHold | null>(null)
  const [error, setError] = useState('')
  function checkout() {
    try {
      setHold(createDemoHold(slots, selectedId ?? '', clinic.tenant_id))
      setError('')
    } catch (cause) {
      setError((cause as Error).message)
      setSelectedId(null)
    }
  }
  return (
    <>
      <p className="mb-6 rounded-lg bg-amber-50 p-3 text-sm text-amber-900">
        Booking preview: these are demo time slots, not the clinic's live
        availability.
      </p>
      {error && <ErrorState message={error} />}
      {hold ? (
        <CheckoutReview
          hold={hold}
          clinicName={clinic.name}
          onBack={() => {
            setHold(null)
            setSelectedId(null)
          }}
        />
      ) : (
        <SlotPicker
          slots={slots}
          dates={dates}
          date={date}
          selectedId={selectedId}
          onDate={(value) => {
            setDate(value)
            setSelectedId(null)
            setError('')
          }}
          onSelect={(id) => {
            setSelectedId(id)
            setError('')
          }}
          onCheckout={checkout}
        />
      )}
    </>
  )
}
