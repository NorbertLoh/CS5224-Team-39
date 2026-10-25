import { apiFetch, ApiError } from '../../lib/api'
import { accessToken } from '../clinics/api'
import type { CursorPage } from '../../lib/api-types'
import type { Medication, Note, Prescription, PrescriptionInput } from './types'
import { prescriptionItems } from './types'
import type { MedicalCertificate } from './medicalCertificate'
import type { Appointment } from '../scheduling/api'

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
export async function previousVisits(
  appointment: Appointment,
  cursor: string | null,
  signal?: AbortSignal,
): Promise<CursorPage<Appointment>> {
  const seen = new Set<string>()
  for (let pageNumber = 0; pageNumber < 100; pageNumber++) {
    const params = new URLSearchParams({
      tenant_id: appointment.tenant_id,
      status: 'completed',
      to: appointment.starts_at,
      period: 'past',
      limit: '100',
    })
    if (cursor) params.set('cursor', cursor)
    const page: CursorPage<Appointment> = await (
      await request(`/scheduling/appointments?${params}`, { signal })
    ).json()
    const items = page.items.filter(
      (visit) =>
        visit.patient_id === appointment.patient_id &&
        visit.doctor_id === appointment.doctor_id &&
        visit.tenant_id === appointment.tenant_id &&
        visit.status === 'completed' &&
        visit.appointment_id !== appointment.appointment_id &&
        Date.parse(visit.starts_at) < Date.parse(appointment.starts_at),
    )
    if (items.length || !page.next_cursor)
      return { items, next_cursor: page.next_cursor }
    if (seen.has(page.next_cursor)) break
    seen.add(page.next_cursor)
    cursor = page.next_cursor
  }
  throw new Error('Could not finish previous visit pagination')
}
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
export async function readMedicalCertificate(
  appointmentId: string,
  signal?: AbortSignal,
): Promise<MedicalCertificate | null> {
  try {
    const result: MedicalCertificate = await (
      await request(
        `${base}/appointments/${id(appointmentId)}/medical-certificate`,
        { signal },
      )
    ).json()
    if (result.appointment_id !== appointmentId)
      throw new Error('Invalid MC context')
    return result
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return null
    throw error
  }
}
export async function saveMedicalCertificate(
  appointmentId: string,
  body: {
    selected: boolean
    start_date: string | null
    duration_days: number | null
    additional_notes: string
  },
): Promise<MedicalCertificate> {
  const result: MedicalCertificate = await (
    await request(
      `${base}/appointments/${id(appointmentId)}/medical-certificate`,
      json('PUT', body),
    )
  ).json()
  if (result.appointment_id !== appointmentId)
    throw new Error('Invalid MC context')
  return result
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
  tenantId: string,
): Promise<Prescription> {
  const resolved = []
  for (const item of prescriptionItems(items)) {
    const medication = item.medication_id
      ? null
      : await registerMedication(tenantId, item.display_name ?? '')
    resolved.push({
      medication_id: item.medication_id || medication!.medication_id,
      quantity: item.quantity,
      instructions: item.instructions,
    })
  }
  return (
    await request(
      prescriptionId
        ? `${base}/prescriptions/${id(prescriptionId)}`
        : `${base}/appointments/${id(appointmentId)}/prescriptions`,
      json(prescriptionId ? 'PATCH' : 'POST', {
        items: resolved,
      }),
    )
  ).json()
}
export async function registerMedication(
  tenantId: string,
  displayName: string,
): Promise<Medication> {
  return (
    await request(
      `/fulfilment/clinics/${id(tenantId)}/catalogue`,
      json('POST', { display_name: displayName.trim() }),
    )
  ).json()
}
export async function priceMedication(
  tenantId: string,
  medication: Medication,
  amountMinor: number,
  unitLabel: string,
): Promise<Medication> {
  return (
    await request(
      `/fulfilment/clinics/${id(tenantId)}/catalogue/${id(medication.medication_id)}`,
      json('PUT', {
        display_name: medication.display_name,
        unit_label: unitLabel.trim(),
        unit_price: { amount_minor: amountMinor, currency: 'SGD' },
        active: true,
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
      return 'Check the note, medications, quantities, instructions and MC dates/duration.'
  }
  return 'Could not complete the records request. Check your connection and reload records. If a save or issuance timed out, reload to check its outcome before trying again.'
}
