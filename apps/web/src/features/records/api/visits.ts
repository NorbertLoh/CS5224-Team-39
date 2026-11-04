import type { Appointment } from '@/features/scheduling/api'
import type { CursorPage } from '@/lib/api-types'
import { request } from './client'

export async function previousVisits(
  appointment: Appointment,
  cursor: string | null,
  signal?: AbortSignal,
  limit = 100,
): Promise<CursorPage<Appointment>> {
  const params = new URLSearchParams({
    history_for: appointment.appointment_id,
    limit: String(limit),
  })
  if (cursor) params.set('cursor', cursor)
  const page: CursorPage<Appointment> = await (
    await request(`/scheduling/appointments?${params}`, { signal })
  ).json()
  if (
    page.items.some(
      (visit) =>
        visit.patient_id !== appointment.patient_id ||
        visit.tenant_id !== appointment.tenant_id ||
        visit.status !== 'completed' ||
        visit.appointment_id === appointment.appointment_id ||
        !(Date.parse(visit.starts_at) < Date.parse(appointment.starts_at)),
    )
  )
    throw new Error('Invalid previous visit context')
  return page
}
