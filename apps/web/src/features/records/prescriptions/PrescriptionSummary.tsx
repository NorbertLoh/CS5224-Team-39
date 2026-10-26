import type { Order } from '@/features/fulfilment/api'
import { medicineProgress } from '@/features/fulfilment/domain/patientMedicines'
import { PatientAccordionItem } from '@/features/patient/components/PatientAccordionItem'
import type { Prescription } from '@/features/records/types'
import { appointmentDetail } from '@/features/scheduling/api'
import { useQuery } from '@tanstack/react-query'
import type { ReactNode } from 'react'

export function PrescriptionSummary({
  prescription,
  token,
  selected,
  onToggle,
  children,
  order,
  checking,
  unavailable,
}: {
  prescription: Prescription
  token: string
  selected: boolean
  onToggle: () => void
  children: ReactNode
  order?: Order
  checking: boolean
  unavailable: boolean
}) {
  const issued = prescription.status === 'issued'
  const label = !issued
    ? prescription.status
    : checking
      ? 'Checking payment'
      : unavailable
        ? 'Payment status unavailable'
        : !order
          ? 'Awaiting payment'
          : order.payment_status === 'succeeded'
            ? `Paid · ${medicineProgress(order)}`
            : medicineProgress(order)
  const colour = !issued
    ? prescription.status === 'voided'
      ? 'bg-red-50 text-red-700 ring-red-200'
      : 'bg-slate-100 text-slate-700 ring-slate-200'
    : checking
      ? 'bg-slate-100 text-slate-700 ring-slate-200'
      : unavailable ||
          (order &&
            (['cancelled', 'exception'].includes(order.status) ||
              ['refund_required', 'refunded'].includes(order.payment_status)))
        ? 'bg-red-50 text-red-700 ring-red-200'
        : order?.payment_status === 'succeeded'
          ? 'bg-emerald-50 text-emerald-800 ring-emerald-200'
          : order?.payment_status === 'pending'
            ? 'bg-blue-50 text-blue-700 ring-blue-200'
            : 'bg-amber-50 text-amber-800 ring-amber-200'
  const appointment = useQuery({
    queryKey: ['records', 'context', token, prescription.appointment_id],
    queryFn: ({ signal }) =>
      appointmentDetail(prescription.appointment_id, signal),
    retry: false,
    gcTime: 0,
  })
  const context = appointment.data
  const clinicName =
    context?.appointment_id === prescription.appointment_id &&
    context.tenant_id === prescription.tenant_id &&
    context.patient_id === prescription.patient_id
      ? context.clinic_name?.trim()
      : undefined
  return (
    <PatientAccordionItem
      title={
        <span className="flex flex-wrap items-center gap-2">
          Prescription
          <span
            className={`rounded-full px-2.5 py-1 text-xs font-medium capitalize ring-1 ring-inset ${colour}`}
          >
            {label}
          </span>
        </span>
      }
      open={selected}
      onToggle={onToggle}
      summary={
        <>
          <span className="block text-sm">
            {new Intl.DateTimeFormat('en-SG', {
              timeZone: 'Asia/Singapore',
              dateStyle: 'medium',
            }).format(
              new Date(prescription.issued_at ?? prescription.created_at),
            )}{' '}
            · {prescription.items.length} medication(s)
          </span>
          <span className="block text-sm">
            Clinic:{' '}
            {clinicName ||
              (appointment.isPending
                ? 'Loading clinic name...'
                : 'Clinic name unavailable')}
          </span>
        </>
      }
    >
      {children}
    </PatientAccordionItem>
  )
}
