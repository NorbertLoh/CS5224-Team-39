import { DocumentRow } from '@/features/documents/DocumentRow'
import { nameOrId } from '@/features/appointments/display'
import { documentKindOrder } from '@/features/documents/pastDocumentGroups'
import type { DocumentMetadata } from '@/features/documents/types'
import { documentNames } from '@/features/documents/types'
import type { Appointment } from '@/features/scheduling/api'
import { ChevronDown } from 'lucide-react'
import { useState } from 'react'

const visitDate = new Intl.DateTimeFormat('en-SG', {
  timeZone: 'Asia/Singapore',
  dateStyle: 'medium',
  timeStyle: 'short',
})

export function PastDocumentRow({
  documents,
  visit,
  token,
  historyFor,
}: {
  documents: DocumentMetadata[]
  visit: Appointment
  token: string
  historyFor?: string
}) {
  const [open, setOpen] = useState(false)
  return (
    <details
      className="group rounded-xl border border-slate-200 bg-slate-50/50"
      onToggle={(event) => setOpen(event.currentTarget.open)}
    >
      <summary className="flex cursor-pointer list-none items-center justify-between gap-3 rounded-lg p-4 focus-visible:outline-2 focus-visible:outline-offset-2 [&::-webkit-details-marker]:hidden">
        <span>
          <span className="block font-medium">
            Consultation · {visitDate.format(new Date(visit.starts_at))} SGT
          </span>
          <span className="block text-sm text-slate-600">
            {nameOrId(visit.doctor_name, visit.doctor_id)}
          </span>
          <span className="block text-sm text-slate-600">
            {documents.length}{' '}
            {documents.length === 1 ? 'document' : 'documents'} ·{' '}
            {documentKindOrder
              .filter((kind) => documents.some((item) => item.kind === kind))
              .map((kind) => documentNames[kind])
              .join(', ')}
          </span>
        </span>
        <ChevronDown
          aria-hidden="true"
          size={20}
          className="shrink-0 text-slate-500 transition-transform group-open:rotate-180"
        />
      </summary>
      {open && (
        <div className="rounded-b-xl border-t border-slate-200 bg-white px-4">
          <ul className="divide-y divide-slate-200">
            {documents.map((document) => (
              <li key={document.document_id}>
                <DocumentRow
                  document={document}
                  token={token}
                  historyFor={historyFor}
                />
              </li>
            ))}
          </ul>
        </div>
      )}
    </details>
  )
}
