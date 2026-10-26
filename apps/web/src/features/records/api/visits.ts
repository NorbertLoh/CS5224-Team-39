import type { Appointment } from '@/features/scheduling/api'
import type { CursorPage } from '@/lib/api-types'
import { request } from './client'

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
