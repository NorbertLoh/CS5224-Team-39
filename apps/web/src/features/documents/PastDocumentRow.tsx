import { DocumentRow } from '@/features/documents/DocumentRow'
import type { DocumentMetadata } from '@/features/documents/types'
import { documentNames, documentStates } from '@/features/documents/types'
import { ChevronDown } from 'lucide-react'
import { useState } from 'react'

const visitDate = new Intl.DateTimeFormat('en-SG', {
  timeZone: 'Asia/Singapore',
  dateStyle: 'medium',
  timeStyle: 'short',
})

export function PastDocumentRow({
  document,
  token,
}: {
  document: DocumentMetadata
  token: string
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
            {visitDate.format(new Date(document.created_at))} SGT
          </span>
          <span className="block text-sm text-slate-600">
            {documentNames[document.kind]} · {documentStates[document.status]}
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
          <DocumentRow document={document} token={token} />
        </div>
      )}
    </details>
  )
}
