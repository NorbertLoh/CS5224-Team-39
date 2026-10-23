import { useState } from 'react'
import { useQueries } from '@tanstack/react-query'
import { PatientAccordionItem } from '../patient/PatientAccordionItem'
import { appointmentDetail } from '../scheduling/api'
import { useAppointmentNames } from '../appointments/useAppointmentNames'
import {
  dateInSingapore,
  formatDate,
  formatTime,
} from '../appointments/display'
import { DocumentRow } from './DocumentRow'
import { documentNames } from './types'
import type { DocumentMetadata } from './types'

const documentOrder = [
  'prescription_pdf',
  'receipt_pdf',
  'medical_certificate_pdf',
] as const

export function VisitDocumentList({
  documents,
  token,
}: {
  documents: DocumentMetadata[]
  token: string
}) {
  const [selected, setSelected] = useState<string | null>(null)
  const visits = new Map<string, DocumentMetadata[]>()
  for (const document of documents) {
    const key = `${document.tenant_id}:${document.appointment_id}`
    const items = visits.get(key) ?? []
    if (!items.some((item) => item.document_id === document.document_id))
      items.push(document)
    visits.set(key, items)
  }
  const groups = [...visits].map(([key, items]) => ({ key, items }))
  const contexts = useQueries({
    queries: groups.map((group) => ({
      queryKey: ['documents', 'visit', token, group.key],
      queryFn: async ({ signal }: { signal: AbortSignal }) => {
        const document = group.items[0]
        const appointment = await appointmentDetail(
          document.appointment_id,
          signal,
        )
        if (
          appointment.appointment_id !== document.appointment_id ||
          appointment.tenant_id !== document.tenant_id
        )
          throw new Error('Visit unavailable')
        return appointment
      },
      staleTime: 60000,
      retry: false,
    })),
  })
  const appointments = useAppointmentNames(
    contexts.flatMap((context) => (context.data ? [context.data] : [])),
  )
  const names = new Map(
    appointments.map((appointment) => [
      `${appointment.tenant_id}:${appointment.appointment_id}`,
      appointment,
    ]),
  )
  const sorted = groups
    .map((group, index) => ({
      ...group,
      appointment: names.get(group.key),
      loading: contexts[index].isPending,
    }))
    .sort((a, b) => {
      const date = (group: typeof a) =>
        group.appointment?.starts_at ??
        group.items.reduce(
          (latest, item) =>
            item.created_at > latest ? item.created_at : latest,
          group.items[0].created_at,
        )
      return (
        Date.parse(date(b)) - Date.parse(date(a)) || a.key.localeCompare(b.key)
      )
    })
  return (
    <ul className="divide-y">
      {sorted.map(({ key, items, appointment, loading }) => (
        <li key={key}>
          <PatientAccordionItem
            title={appointment?.clinic_name || 'Visit documents'}
            summary={
              <>
                <span className="block">
                  {appointment
                    ? `${formatDate(dateInSingapore(appointment.starts_at))} · ${formatTime(appointment.starts_at)}–${formatTime(appointment.ends_at)} SGT`
                    : loading
                      ? 'Loading visit information...'
                      : 'Visit information unavailable'}
                </span>
                {appointment && (
                  <span className="block">{appointment.doctor_name}</span>
                )}
                <span className="block">
                  {items.length} {items.length === 1 ? 'document' : 'documents'}{' '}
                  ·{' '}
                  {documentOrder
                    .filter((kind) => items.some((item) => item.kind === kind))
                    .map((kind) => documentNames[kind])
                    .join(', ')}
                </span>
              </>
            }
            open={selected === key}
            onToggle={() =>
              setSelected((current) => (current === key ? null : key))
            }
          >
            <ul className="divide-y">
              {[...items]
                .sort(
                  (a, b) =>
                    documentOrder.indexOf(a.kind) -
                      documentOrder.indexOf(b.kind) ||
                    Date.parse(b.created_at) - Date.parse(a.created_at),
                )
                .map((document) => (
                  <li key={document.document_id}>
                    <DocumentRow document={document} token={token} />
                  </li>
                ))}
            </ul>
          </PatientAccordionItem>
        </li>
      ))}
    </ul>
  )
}
