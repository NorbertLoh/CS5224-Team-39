import { useEffect, useRef } from 'react'
import { consultationPrice } from '../../lib/money'
import {
  clinicName,
  dateInSingapore,
  formatDate,
  formatTime,
  readableStatus,
  subjectName,
} from './fixtures'
import type { Appointment } from './fixtures'

export function AppointmentDetails({
  appointment,
  onClose,
}: {
  appointment: Appointment
  onClose: () => void
}) {
  const heading = useRef<HTMLHeadingElement>(null)
  useEffect(() => {
    heading.current?.focus()
  }, [appointment.appointment_id])
  const fields = [
    ['Patient', subjectName(appointment.patient_id)],
    ['Doctor', subjectName(appointment.doctor_id)],
    ['Clinic', clinicName(appointment.tenant_id)],
    ['Date', formatDate(dateInSingapore(appointment.starts_at))],
    [
      'Time (Singapore)',
      `${formatTime(appointment.starts_at)}–${formatTime(appointment.ends_at)}`,
    ],
    ['Status', readableStatus(appointment.status)],
    [
      'Consultation fee',
      consultationPrice(
        appointment.consultation_price.amount_minor,
        appointment.consultation_price.currency,
      ),
    ],
    ['Payment resolution', readableStatus(appointment.payment_resolution)],
    [
      'Hold expires',
      appointment.hold_expires_at
        ? `${formatDate(dateInSingapore(appointment.hold_expires_at))}, ${formatTime(appointment.hold_expires_at)} SGT`
        : 'No active hold',
    ],
    ['Appointment ID', appointment.appointment_id],
  ]
  return (
    <section
      aria-labelledby="appointment-details-heading"
      className="rounded-xl border bg-white p-5"
    >
      <div className="flex items-center justify-between gap-4">
        <h3
          ref={heading}
          tabIndex={-1}
          id="appointment-details-heading"
          className="text-xl font-semibold"
        >
          Appointment details
        </h3>
        <button
          type="button"
          className="rounded border px-3 py-2 text-sm focus-visible:outline-2"
          onClick={onClose}
        >
          Close details
        </button>
      </div>
      <dl className="mt-4 grid gap-4 sm:grid-cols-2">
        {fields.map(([label, value]) => (
          <div key={label}>
            <dt className="text-sm text-slate-500">{label}</dt>
            <dd className="break-words font-medium capitalize">{value}</dd>
          </div>
        ))}
      </dl>
      {appointment.payment_resolution === 'refund_required' && (
        <p className="mt-4 text-sm text-amber-800">
          Payment needs a refund review. This appointment is not confirmed by
          that payment.
        </p>
      )}
    </section>
  )
}
