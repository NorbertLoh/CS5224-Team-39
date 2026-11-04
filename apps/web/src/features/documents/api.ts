import { accessToken } from '@/auth/access-token'
import type { DocumentMetadata } from '@/features/documents/types'
import { ApiError, apiFetch } from '@/lib/api'
import type { CursorPage } from '@/lib/api-types'
import { usesAws } from '@/lib/backend-config'

const base = '/document/documents'
async function request(path: string, signal?: AbortSignal) {
  return apiFetch(path, {
    accessToken: await accessToken(),
    signal: signal
      ? AbortSignal.any([signal, AbortSignal.timeout(15000)])
      : AbortSignal.timeout(15000),
  })
}

export async function listDocuments(
  appointmentId?: string,
  cursor?: string | null,
  signal?: AbortSignal,
): Promise<CursorPage<DocumentMetadata>> {
  const params = new URLSearchParams({ limit: '25' })
  if (appointmentId) params.set('appointment_id', appointmentId)
  if (cursor) params.set('cursor', cursor)
  const page: CursorPage<DocumentMetadata> = await (
    await request(`${base}?${params}`, signal)
  ).json()
  if (
    appointmentId &&
    page.items.some((item) => item.appointment_id !== appointmentId)
  )
    throw new Error('Invalid document context')
  return page
}

export function validateDownload(
  value: { download_url: string; expires_at: string },
  aws = usesAws(),
) {
  const url = new URL(value.download_url)
  const local =
    !aws &&
    url.protocol === 'http:' &&
    ['localhost', '127.0.0.1'].includes(url.hostname)
  if (
    (!local && url.protocol !== 'https:') ||
    url.username ||
    url.password ||
    url.hash ||
    !Number.isFinite(Date.parse(value.expires_at)) ||
    Date.parse(value.expires_at) <= Date.now()
  )
    throw new Error('Invalid or expired document download')
  return url.href
}

export async function documentDownloadUrl(
  documentId: string,
  signal?: AbortSignal,
) {
  const result = await (
    await request(`${base}/${encodeURIComponent(documentId)}/download`, signal)
  ).json()
  return validateDownload(result)
}

export function documentsError(error: unknown) {
  if (error instanceof ApiError) {
    if (error.status === 401)
      return 'Your session expired. Please sign in again.'
    if (error.status === 403 || error.status === 404)
      return 'These documents are unavailable to your account.'
    if (error.status === 409)
      return 'This PDF is not ready. Refresh documents to check its status.'
    if (error.status === 422)
      return 'The document list changed. Refresh documents to start again.'
  }
  return 'Could not load or download documents. Check your connection and try again.'
}
