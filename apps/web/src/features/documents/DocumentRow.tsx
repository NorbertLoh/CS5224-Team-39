import { documentDate, documentStates } from './types'
import { useDocumentName } from './useDocumentName'
import { useDocumentDownload } from './useDocumentDownload'
import type { DocumentMetadata } from './types'

export function DocumentRow({
  document: item,
  token,
}: {
  document: DocumentMetadata
  token: string
}) {
  const name = useDocumentName(item, token)
  const { busy, error, requested, download } = useDocumentDownload(item)

  return (
    <article className="space-y-3 py-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 space-y-1">
          <h3 className="font-medium">{name}</h3>
          <p className="text-sm text-slate-600">
            <time dateTime={item.created_at}>
              {documentDate(item.created_at)} SGT
            </time>
          </p>
          <p className="text-sm">{documentStates[item.status]}</p>
          <details className="text-xs text-slate-500">
            <summary className="cursor-pointer">Document reference</summary>
            <p className="mt-1 break-all">{item.document_id}</p>
            <p className="mt-1 break-all">Appointment: {item.appointment_id}</p>
          </details>
        </div>
        {item.status === 'ready' && (
          <button
            type="button"
            aria-label={`Download ${name} PDF`}
            className="rounded-lg bg-slate-900 px-4 py-2 text-sm text-white disabled:opacity-50"
            disabled={busy}
            onClick={() => void download()}
          >
            {busy ? 'Preparing download...' : 'Download PDF'}
          </button>
        )}
      </div>
      {item.status === 'failed' && (
        <p className="text-sm text-slate-600">
          This PDF could not be prepared. Contact your clinic if it remains
          unavailable.
        </p>
      )}
      {error && (
        <p role="alert" className="text-sm text-red-700">
          {error} You can try the download again.
        </p>
      )}
      {requested && (
        <p role="status" className="text-sm text-slate-600">
          Download requested. If it did not start, select Download PDF again.
        </p>
      )}
    </article>
  )
}
