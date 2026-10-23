import type { Prescription } from './types'
import { useQuery } from '@tanstack/react-query'
import { appointmentDetail } from '../scheduling/api'
import type { ReactNode } from 'react'
import { PatientAccordionItem } from '../patient/PatientAccordionItem'

export function PrescriptionSummary({
  prescription,
  token,
  selected,
  onToggle,
  children,
}: {
  prescription: Prescription
  token: string
  selected: boolean
  onToggle: () => void
  children: ReactNode
}) {
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
        <>
          Prescription ·{' '}
          <span className="capitalize">{prescription.status}</span>
        </>
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
