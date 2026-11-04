import { canCheckout } from '@/features/checkout/live'
import type { Appointment } from '@/features/scheduling/api'
import { useEffect, useState } from 'react'

export function AppointmentPaymentAction({
  appointment,
}: {
  appointment: Appointment
}) {
  const [now, setNow] = useState(Date.now)
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(timer)
  }, [])

  if (
    !['none', 'awaiting_payment'].includes(appointment.payment_resolution) ||
    !canCheckout(appointment, null, now)
  )
    return null

  return (
    <a
      className="inline-block rounded border px-4 py-3 focus-visible:outline-2 focus-visible:outline-offset-2"
      href={`/patient/checkout?appointment_id=${encodeURIComponent(appointment.appointment_id)}`}
    >
      Pay consultation fee
    </a>
  )
}
