import { apiFetch, ApiError } from '../../lib/api'
import { accessToken } from '../clinics/api'
import type { CursorPage } from '../../lib/api-types'
import type { Medication, Note, Prescription, PrescriptionInput } from './types'
import { prescriptionItems } from './types'

async function request(path: string, init: RequestInit = {}) {
  return apiFetch(path, {
    ...init,
    accessToken: await accessToken(),
    signal: init.signal
      ? AbortSignal.any([init.signal, AbortSignal.timeout(15000)])
      : AbortSignal.timeout(15000),
  })
}
const base = '/clinical-records'
const id = encodeURIComponent
function json(method: string, body: unknown): RequestInit {
  return {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }
}
export async function readNote(
  appointmentId: string,
  signal?: AbortSignal,
): Promise<Note | null> {
  try {
    return await (
      await request(`${base}/appointments/${id(appointmentId)}/note`, {
        signal,
      })
    ).json()
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return null
    throw error
  }
}
export async function saveNote(
  appointmentId: string,
  text: string,
): Promise<Note> {
  return (
    await request(
      `${base}/appointments/${id(appointmentId)}/note`,
      json('PUT', { text: text.trim() }),
    )
  ).json()
}
export async function listPrescriptions(
  appointmentId?: string,
  cursor?: string | null,
  signal?: AbortSignal,
): Promise<CursorPage<Prescription>> {
  const params = new URLSearchParams({ limit: '25' })
  if (appointmentId) params.set('appointment_id', appointmentId)
  if (cursor) params.set('cursor', cursor)
  return (await request(`${base}/prescriptions?${params}`, { signal })).json()
}
export async function readPrescription(
  prescriptionId: string,
  signal?: AbortSignal,
): Promise<Prescription> {
  return (
    await request(`${base}/prescriptions/${id(prescriptionId)}`, { signal })
  ).json()
}
export async function appointmentPrescriptions(
  appointmentId: string,
  signal?: AbortSignal,
): Promise<Prescription[]> {
  const items: Prescription[] = []
  const seen = new Set<string>()
  let cursor: string | null = null
  for (let pageNumber = 0; pageNumber < 100; pageNumber++) {
    const page = await listPrescriptions(appointmentId, cursor, signal)
    if (page.items.some((item) => item.appointment_id !== appointmentId))
      throw new Error('Invalid prescription context')
    items.push(...page.items)
    cursor = page.next_cursor
    if (!cursor) return items
    if (seen.has(cursor)) break
    seen.add(cursor)
  }
  throw new Error('Invalid prescription pagination')
}
export async function savePrescription(
  appointmentId: string,
  prescriptionId: string | undefined,
  items: PrescriptionInput[],
): Promise<Prescription> {
  return (
    await request(
      prescriptionId
        ? `${base}/prescriptions/${id(prescriptionId)}`
        : `${base}/appointments/${id(appointmentId)}/prescriptions`,
      json(prescriptionId ? 'PATCH' : 'POST', {
        items: prescriptionItems(items),
      }),
    )
  ).json()
}
export async function issuePrescription(
  prescriptionId: string,
): Promise<Prescription> {
  return (
    await request(
      `${base}/prescriptions/${id(prescriptionId)}/issue`,
      json('POST', {}),
    )
  ).json()
}
export async function catalogue(
  tenantId: string,
  signal?: AbortSignal,
): Promise<Medication[]> {
  const items: Medication[] = []
  const seen = new Set<string>()
  let cursor: string | null = null
  for (let pageNumber = 0; pageNumber < 100; pageNumber++) {
    const params = new URLSearchParams({ limit: '100' })
    if (cursor) params.set('cursor', cursor)
    const page: CursorPage<Medication> = await (
      await request(`/fulfilment/clinics/${id(tenantId)}/catalogue?${params}`, {
        signal,
      })
    ).json()
    if (page.items.some((item) => item.tenant_id !== tenantId))
      throw new Error('Invalid catalogue context')
    items.push(...page.items.filter((item) => item.active))
    cursor = page.next_cursor
    if (!cursor) return items
    if (seen.has(cursor)) break
    seen.add(cursor)
  }
  throw new Error('Invalid catalogue pagination')
}
export function recordsError(error: unknown) {
  if (error instanceof ApiError) {
    if (error.status === 401)
      return 'Your session expired. Please sign in again.'
    if (error.status === 403 || error.status === 404)
      return 'This record or appointment is unavailable to your account.'
    if (error.status === 409)
      return 'The appointment, prescription or catalogue changed. Reload records before continuing.'
    if (error.status === 422)
      return 'Check the note, medications, quantities and instructions.'
  }
  return 'Could not complete the records request. Check your connection and reload records. If a save or issuance timed out, reload to check its outcome before trying again.'
}
