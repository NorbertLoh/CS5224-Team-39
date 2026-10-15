import { apiFetch, ApiError } from '../../lib/api'
import { accessToken } from '../clinics/api'
import type { CursorPage } from '../../lib/api-types'
import type {
  SlotPublic as Slot,
  AppointmentPublic as Appointment,
} from './types.generated'
export type {
  SlotPublic as Slot,
  AppointmentPublic as Appointment,
} from './types.generated'

async function request(
  path: string,
  init: RequestInit = {},
  authenticated = true,
) {
  return apiFetch(`/scheduling${path}`, {
    ...init,
    accessToken: authenticated ? await accessToken() : undefined,
    signal: init.signal ?? AbortSignal.timeout(15000),
  })
}

function json(method: string, body: unknown): RequestInit {
  return {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }
}

export async function listSlots(
  tenantId: string,
  from: string,
  to: string,
  doctorId?: string,
  signal?: AbortSignal,
): Promise<Slot[]> {
  const query = new URLSearchParams({ from, to, limit: '100' })
  if (doctorId) query.set('doctor_id', doctorId)
  const items: Slot[] = []
  let cursor: string | null = null
  do {
    if (cursor) query.set('cursor', cursor)
    const page: CursorPage<Slot> = await (
      await request(
        `/clinics/${encodeURIComponent(tenantId)}/slots?${query}`,
        { signal },
        false,
      )
    ).json()
    items.push(...page.items)
    cursor = page.next_cursor
  } while (cursor)
  return items
}

export async function createSlot(
  tenantId: string,
  startsAt: string,
): Promise<Slot> {
  return (
    await request(
      `/clinics/${encodeURIComponent(tenantId)}/slots`,
      json('POST', {
        starts_at: startsAt,
        ends_at: new Date(Date.parse(startsAt) + 1800000).toISOString(),
      }),
    )
  ).json()
}
export async function removeSlot(slotId: string) {
  await request(`/slots/${encodeURIComponent(slotId)}`, { method: 'DELETE' })
}
export async function createHold(
  tenantId: string,
  slotId: string,
): Promise<Appointment> {
  return (
    await request(
      '/appointments',
      json('POST', { tenant_id: tenantId, slot_id: slotId }),
    )
  ).json()
}
export async function listAppointments(
  tenantId?: string,
  cursor?: string | null,
  signal?: AbortSignal,
): Promise<CursorPage<Appointment>> {
  const query = new URLSearchParams({ limit: '100' })
  if (tenantId) query.set('tenant_id', tenantId)
  if (cursor) query.set('cursor', cursor)
  return (await request(`/appointments?${query}`, { signal })).json()
}
export async function appointmentDetail(id: string): Promise<Appointment> {
  return (await request(`/appointments/${encodeURIComponent(id)}`)).json()
}
export async function cancelAppointment(
  id: string,
  reason: string,
): Promise<Appointment> {
  return (
    await request(
      `/appointments/${encodeURIComponent(id)}/cancel`,
      json('POST', { reason }),
    )
  ).json()
}

export function schedulingError(error: unknown) {
  if (error instanceof ApiError) {
    if (error.status === 409)
      return 'This slot or appointment changed. Refresh and choose again.'
    if (error.status === 401)
      return 'Your session expired. Please sign in again.'
    if (error.status === 403)
      return 'Your current role or clinic membership does not allow this action.'
    if (error.status === 404)
      return 'This clinic, slot or appointment is no longer accessible.'
    if (error.status === 422)
      return 'Check the selected times or cancellation reason and try again.'
  }
  return 'Could not complete the scheduling request. Check your connection and refresh. If a booking timed out, check Appointments before trying again.'
}

export function canCancel(appointment: Appointment, now = Date.now()) {
  if (appointment.status === 'held' || appointment.status === 'pending_payment')
    return Boolean(
      appointment.hold_expires_at &&
        Date.parse(appointment.hold_expires_at) > now,
    )
  return (
    appointment.status === 'confirmed' &&
    Date.parse(appointment.starts_at) > now
  )
}
