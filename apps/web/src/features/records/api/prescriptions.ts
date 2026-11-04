import { prescriptionItems } from '@/features/records/domain/prescriptions'
import type {
  Medication,
  Prescription,
  PrescriptionInput,
} from '@/features/records/types'
import type { CursorPage } from '@/lib/api-types'
import { base, id, json, request } from './client'

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
