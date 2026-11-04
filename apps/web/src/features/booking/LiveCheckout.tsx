import { ErrorState } from '@/components/ErrorState'
import type { Appointment } from '@/features/scheduling/api'
import {
  appointmentDetail,
  canCancel,
  cancelAppointment,
  schedulingError,
} from '@/features/scheduling/api'
import { consultationPrice } from '@/lib/money'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'

export function LiveCheckout({
  appointment,
  clinicName,
  doctorName,
  token,
  onBack,
}: {
  appointment: Appointment
  clinicName: string
  doctorName: string
  token?: string
  onBack: () => void
}) {
  const cache = useQueryClient()
  const [now, setNow] = useState(Date.now)
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(timer)
  }, [])
  const detail = useQuery({
    queryKey: ['scheduling', 'appointment', token, appointment.appointment_id],
    queryFn: () => appointmentDetail(appointment.appointment_id),
    refetchInterval: 5000,
    refetchOnWindowFocus: true,
  })
  const current = detail.data ?? appointment
  const seconds = current.hold_expires_at
    ? Math.max(0, Math.ceil((Date.parse(current.hold_expires_at) - now) / 1000))
    : 0
  const release = useMutation({
    mutationFn: () =>
      cancelAppointment(
        current.appointment_id,
        'Patient changed booking time before checkout.',
      ),
    onSuccess: onBack,
    onSettled: async () => {
      await cache.invalidateQueries({ queryKey: ['scheduling'] })
    },
    retry: false,
  })
  const active = canCancel(current, now)
  return (
    <section
      className="mx-auto max-w-xl space-y-4 rounded-2xl border bg-white p-6"
      aria-labelledby="checkout-heading"
    >
      <h2 id="checkout-heading" className="text-2xl font-semibold">
        Booking hold
      </h2>
      <p>
        {clinicName} · {doctorName}
      </p>
      <p>
        {new Date(current.starts_at).toLocaleString('en-SG', {
          timeZone: 'Asia/Singapore',
        })}{' '}
        SGT
      </p>
      <p>
        Consultation fee:{' '}
        {consultationPrice(
          current.consultation_price.amount_minor,
          current.consultation_price.currency,
        )}
      </p>
      <p className="break-words text-sm">
        Appointment: {current.appointment_id}
      </p>
      <p role="status">
        {current.status === 'held' || current.status === 'pending_payment'
          ? seconds
            ? `Hold expires in ${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}.`
            : 'This hold has expired. Choose another time.'
          : `Appointment status: ${current.status.replaceAll('_', ' ')}`}
      </p>
      <p className="text-sm text-slate-600">
        Your time is reserved until the server deadline. Continue to payment to
        open secure checkout or check its latest status.
      </p>
      <a
        className="inline-block rounded border px-4 py-3"
        href={`/patient/checkout?appointment_id=${current.appointment_id}`}
      >
        Continue to payment
      </a>
      {detail.isError && (
        <ErrorState
          message={schedulingError(detail.error)}
          onRetry={() => void detail.refetch()}
        />
      )}
      {release.isError && (
        <ErrorState message={schedulingError(release.error)} />
      )}
      <button
        type="button"
        disabled={release.isPending || (active && detail.isError)}
        onClick={() => (active ? release.mutate() : onBack())}
        className="rounded border px-4 py-3"
      >
        {release.isPending
          ? 'Releasing hold...'
          : active
            ? 'Release booking and change time'
            : 'Back to available times'}
      </button>
    </section>
  )
}
