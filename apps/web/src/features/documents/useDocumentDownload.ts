import { useEffect, useRef, useState } from 'react'
import { documentDownloadUrl, documentsError } from './api'
import type { DocumentMetadata } from './types'

export function useDocumentDownload(item: DocumentMetadata) {
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

  return { busy, error, requested, download }
}
