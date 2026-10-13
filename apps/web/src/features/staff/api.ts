import { apiFetch } from '@/lib/api'
import type { CursorPage } from '@/lib/api-types'
import { accessToken } from '../clinics/api'

export type StaffRole = 'doctor' | 'clinic_admin'
export type Membership = {
  membership_id: string
  subject_id: string
  tenant_id: string
  roles: StaffRole[]
  status: 'active' | 'revoked'
}

async function request(tenantId: string, suffix: string, options: RequestInit = {}) {
  return apiFetch(`/identity/clinics/${encodeURIComponent(tenantId)}/memberships${suffix}`, {
    ...options, accessToken: await accessToken(),
  })
}

export async function listStaff(tenantId: string, cursor: string | null, signal?: AbortSignal): Promise<CursorPage<Membership>> {
  const query = new URLSearchParams({ limit: '25' })
  if (cursor) query.set('cursor', cursor)
  return (await request(tenantId, `?${query}`, { signal })).json()
}

export async function saveStaff(tenantId: string, subjectId: string, roles: StaffRole[]): Promise<Membership> {
  return (await request(tenantId, `/${encodeURIComponent(subjectId)}`, {
    method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ roles }),
  })).json()
}

export async function revokeStaff(tenantId: string, subjectId: string): Promise<void> {
  await request(tenantId, `/${encodeURIComponent(subjectId)}`, { method: 'DELETE' })
}
