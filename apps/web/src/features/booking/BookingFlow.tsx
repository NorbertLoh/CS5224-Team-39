import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import type { Clinic, Doctor } from '../clinics/api'
import { readSession } from '../../auth/session'
import { ErrorState } from '../../components/ErrorState'
import { LoadingState } from '../../components/LoadingState'
import { createHold, listSlots, schedulingError } from '../scheduling/api'
import type { Appointment } from '../scheduling/api'
import { dayStart, shiftDate, singaporeDate } from '../scheduling/time'
import { SlotPicker } from './SlotPicker'
import { LiveCheckout } from './LiveCheckout'

export function BookingFlow({
  clinic,
  doctors,
}: {
  clinic: Clinic
  doctors: Doctor[]
}) {
  const cache = useQueryClient()
  const token = readSession()?.accessToken
  const [date, setDate] = useState(() => singaporeDate())
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [hold, setHold] = useState<Appointment | null>(null)
  const slots = useQuery({
    queryKey: ['scheduling', 'slots', clinic.tenant_id, date],
    queryFn: ({ signal }) =>
      listSlots(
        clinic.tenant_id,
        dayStart(date),
        dayStart(shiftDate(date, 1)),
        undefined,
        signal,
      ),
    refetchInterval: 15000,
    refetchOnWindowFocus: true,
  })
  const booking = useMutation({
    mutationFn: async () => {
      if (
        !selectedId ||
        !slots.data?.some(
          (slot) =>
            slot.slot_id === selectedId && slot.availability === 'available',
        )
      )
        throw new Error('Select an available slot.')
      return createHold(clinic.tenant_id, selectedId)
    },
    onSuccess: (appointment) => setHold(appointment),
    onSettled: async () => {
      setSelectedId(null)
      await cache.invalidateQueries({ queryKey: ['scheduling'] })
    },
    retry: false,
  })
  return (
    <>
      {booking.isError && (
        <ErrorState message={schedulingError(booking.error)} />
      )}
      {hold ? (
        <LiveCheckout
          key={hold.appointment_id}
          appointment={hold}
          clinicName={clinic.name}
          doctorName={
            doctors.find((doctor) => doctor.doctor_id === hold.doctor_id)
              ?.display_name ?? hold.doctor_id
          }
          token={token}
          onBack={() => {
            setHold(null)
            booking.reset()
            void slots.refetch()
          }}
        />
      ) : (
        <fieldset disabled={booking.isPending} className="space-y-4">
          <label className="flex max-w-sm flex-col gap-2">
            Booking date
            <input
              type="date"
              className="rounded border p-2"
              min={singaporeDate()}
              value={date}
              onChange={(event) => {
                if (event.target.value) {
                  setDate(event.target.value)
                  setSelectedId(null)
                  booking.reset()
                }
              }}
            />
          </label>
          {slots.isPending ? (
            <LoadingState message="Loading live consultation times..." />
          ) : slots.isError ? (
            <ErrorState
              message={schedulingError(slots.error)}
              onRetry={() => void slots.refetch()}
            />
          ) : (
            <SlotPicker
              slots={slots.data.map((slot) => ({
                ...slot,
                doctor_name:
                  doctors.find((doctor) => doctor.doctor_id === slot.doctor_id)
                    ?.display_name ?? slot.doctor_id,
              }))}
              dates={[date]}
              date={date}
              selectedId={selectedId}
              onDate={() => {}}
              onSelect={setSelectedId}
              onCheckout={() => booking.mutate()}
            />
          )}
          <p role="status">
            {booking.isPending ? 'Reserving your selected time...' : ''}
          </p>
          <a className="text-sm underline" href="/patient">
            View your appointments, including existing holds
          </a>
        </fieldset>
      )}
    </>
  )
}
