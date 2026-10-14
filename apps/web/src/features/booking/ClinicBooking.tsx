import { useState } from 'react'
import { useInfiniteQuery, useQuery } from '@tanstack/react-query'
import { publicClinic, clinicDoctors } from '../clinics/api'
import type { Clinic, Doctor } from '../clinics/api'
import { ErrorState } from '../../components/ErrorState'
import { LoadingState } from '../../components/LoadingState'
import { bookingDates, createDemoHold, demoSlots } from './fixtures'
import type { BookingHold } from './fixtures'
import { SlotPicker } from './SlotPicker'
import { CheckoutReview } from './CheckoutReview'

function BookingFlow({
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

export function ClinicBooking({ slug }: { slug: string }) {
  const clinic = useQuery({
    queryKey: ['public-clinic', slug],
    queryFn: () => publicClinic(slug),
  })
  const tenantId = clinic.data?.tenant_id
  const doctors = useInfiniteQuery({
    queryKey: ['clinic-doctors', tenantId],
    initialPageParam: null as string | null,
    queryFn: ({ pageParam }) => clinicDoctors(tenantId!, pageParam),
    enabled: Boolean(tenantId && clinic.data?.status === 'active'),
    getNextPageParam: (page) => page.next_cursor ?? undefined,
  })
  if (clinic.isPending) return <LoadingState message="Loading clinic..." />
  if (clinic.isError)
    return (
      <ErrorState
        message="Could not load the clinic."
        onRetry={() => void clinic.refetch()}
      />
    )
  if (clinic.data.status !== 'active')
    return <ErrorState message="This clinic is not accepting bookings." />
  if (doctors.isPending)
    return <LoadingState message="Loading consultation times..." />
  if (doctors.isError)
    return (
      <ErrorState
        message="Could not load clinic doctors."
        onRetry={() => void doctors.refetch()}
      />
    )
  return (
    <main className="mx-auto max-w-4xl space-y-6 px-6 py-10">
      <a
        href={`/clinics/${encodeURIComponent(slug)}`}
        className="text-sm underline"
      >
        Back to clinic
      </a>
      <h1 className="text-3xl font-semibold">Book at {clinic.data.name}</h1>
      <BookingFlow
        key={clinic.data.tenant_id}
        clinic={clinic.data}
        doctors={doctors.data.pages.flatMap((page) => page.items)}
      />
      {doctors.hasNextPage && (
        <button
          type="button"
          disabled={doctors.isFetchingNextPage}
          onClick={() => void doctors.fetchNextPage()}
          className="rounded border px-4 py-2"
        >
          Load more doctors' times
        </button>
      )}
    </main>
  )
}
