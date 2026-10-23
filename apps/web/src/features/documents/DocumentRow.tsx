import { useEffect, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { paymentDetail } from '../payments/api'
import { documentDownloadUrl, documentsError } from './api'
import { documentDate, documentNames, documentStates } from './types'
import type { DocumentMetadata } from './types'

export function DocumentRow({
  document: item,
  token,
}: {
  document: DocumentMetadata
  token: string
}) {
  const payment = useQuery({
    queryKey: ['documents', 'receipt-payment', token, item.payment_id],
    queryFn: ({ signal }) => paymentDetail(item.payment_id!, signal),
    enabled: item.kind === 'receipt_pdf' && !!item.payment_id,
    staleTime: 60000,
    retry: false,
  })
  const purpose =
    payment.data?.payment_id === item.payment_id &&
    payment.data?.tenant_id === item.tenant_id
      ? payment.data.purpose
      : undefined
  const name =
    item.kind === 'receipt_pdf' && purpose === 'consultation'
      ? 'Consultation receipt'
      : item.kind === 'receipt_pdf' && purpose === 'medication_delivery'
        ? 'Medicines & delivery receipt'
        : documentNames[item.kind]
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [requested, setRequested] = useState(false)
  const controller = useRef<AbortController | null>(null)
  useEffect(() => () => controller.current?.abort(), [])

  async function download() {
    if (controller.current || item.status !== 'ready') return
    const pending = new AbortController()
    controller.current = pending
    setBusy(true)
    setError(null)
    setRequested(false)
    try {
      const url = await documentDownloadUrl(item.document_id, pending.signal)
      if (pending.signal.aborted) return
      const link = window.document.createElement('a')
      link.href = url
      link.referrerPolicy = 'no-referrer'
      link.download = `${item.document_id}.pdf`
      window.document.body.append(link)
      link.click()
      link.remove()
      setRequested(true)
    } catch (failure) {
      if (!pending.signal.aborted) setError(documentsError(failure))
    } finally {
      if (!pending.signal.aborted) setBusy(false)
      controller.current = null
    }
  }

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
