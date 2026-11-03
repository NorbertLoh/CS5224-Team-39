import { accessToken } from '@/auth/access-token'
import { apiFetch } from '@/lib/api'

export type DoctorApplication = {
  subject_id: string
  legal_name: string
  licence_number: string
  licensing_authority: string
  specialty: string
  document_id: string
  status: 'pending' | 'approved' | 'rejected'
  revision: number
  rejection_reason: string | null
  submitted_at: string
  reviewed_at: string | null
}
export type ApplicationFields = Pick<
  DoctorApplication,
  'legal_name' | 'licence_number' | 'licensing_authority' | 'specialty'
>
export type ReviewEvent = {
  event_id: string
  action: string
  actor_id: string
  created_at: string
  snapshot: DoctorApplication & { review_reason?: string }
}

async function request(path: string, options: RequestInit = {}) {
  return apiFetch(`/identity${path}`, {
    ...options,
    accessToken: await accessToken(),
  })
}

export async function myApplication(
  signal?: AbortSignal,
): Promise<DoctorApplication | null> {
  return (await request('/me/doctor-application', { signal })).json()
}

export async function uploadEvidence(file: File): Promise<string> {
  const result = await request('/me/doctor-documents', {
    method: 'POST',
    headers: { 'Content-Type': file.type },
    body: file,
  })
  return ((await result.json()) as { document_id: string }).document_id
}

export async function submitApplication(
  fields: ApplicationFields,
  documentId: string,
  revision: number,
): Promise<DoctorApplication> {
  return (
    await request('/me/doctor-application', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        ...fields,
        document_id: documentId,
        expected_revision: revision,
      }),
    })
  ).json()
}

export async function downloadEvidence(documentId: string) {
  const response = await request(
    `/doctor-documents/${encodeURIComponent(documentId)}`,
  )
  const blob = await response.blob()
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  const extension =
    { 'application/pdf': 'pdf', 'image/png': 'png', 'image/jpeg': 'jpg' }[
      blob.type
    ] ?? 'bin'
  const disposition = response.headers.get('Content-Disposition') ?? ''
  const encodedName = /filename\*=UTF-8''([^;]+)/i.exec(disposition)?.[1]
  link.download = encodedName
    ? decodeURIComponent(encodedName)
    : `Doctor - licence.${extension}`
  link.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

export async function listApplications(
  status: DoctorApplication['status'],
  after: string | null,
  signal?: AbortSignal,
): Promise<DoctorApplication[]> {
  const params = new URLSearchParams({ status, limit: '25' })
  if (after) params.set('after', after)
  return (
    await request(`/platform/doctor-applications?${params}`, { signal })
  ).json()
}

export async function reviewApplication(
  application: DoctorApplication,
  decision: 'approved' | 'rejected',
  reason: string,
): Promise<DoctorApplication> {
  return (
    await request(
      `/platform/doctor-applications/${application.subject_id}/review`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          decision,
          reason,
          expected_revision: application.revision,
        }),
      },
    )
  ).json()
}

export async function applicationHistory(
  subjectId: string,
): Promise<ReviewEvent[]> {
  return (
    await request(`/platform/doctor-applications/${subjectId}/history`)
  ).json()
}
