import { documentDownloadUrl, documentsError } from '@/features/documents/api'
import type { DocumentMetadata } from '@/features/documents/types'
import { useEffect, useRef, useState } from 'react'

export function useDocumentDownload(item: DocumentMetadata, historyFor?: string) {
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
      const url = await documentDownloadUrl(item.document_id, pending.signal, historyFor)
      if (pending.signal.aborted) {
        if (url.startsWith('blob:')) URL.revokeObjectURL(url)
        return
      }
      const link = window.document.createElement('a')
      link.href = url
      link.referrerPolicy = 'no-referrer'
      link.download = `${item.document_id}.pdf`
      window.document.body.append(link)
      link.click()
      link.remove()
      if (url.startsWith('blob:'))
        window.setTimeout(() => URL.revokeObjectURL(url), 60000)
      setRequested(true)
    } catch (failure) {
      if (!pending.signal.aborted) setError(documentsError(failure))
    } finally {
      if (!pending.signal.aborted) setBusy(false)
      controller.current = null
    }
  }

  return { busy, error, requested, download }
}
