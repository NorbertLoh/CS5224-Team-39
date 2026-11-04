import { accessToken } from '@/auth/access-token'
import type { ClinicProfile } from '@/features/clinic-profile/profile'
import { apiFetch } from '@/lib/api'
import type { CursorPage } from '@/lib/api-types'

export type Clinic = ClinicProfile & {
  tenant_id: string
  slug: string
  status: 'pending_review' | 'active' | 'rejected' | 'suspended'
}

export type Doctor = { doctor_id: string; display_name: string }

export async function clinicRequest(
  path: string,
  options: RequestInit = {},
  authenticated = false,
) {
  return apiFetch(`/tenant${path}`, {
    ...options,
    accessToken: authenticated ? await accessToken() : undefined,
  })
}

export async function listClinics(
  cursor: string | null = null,
  admin = false,
): Promise<CursorPage<Clinic>> {
  const query = new URLSearchParams({ limit: '25' })
  if (cursor) query.set('cursor', cursor)
  return (
    await clinicRequest(`${admin ? '/admin' : ''}/clinics?${query}`, {}, admin)
  ).json()
}

export async function publicClinic(slug: string): Promise<Clinic> {
  return (
    await clinicRequest(`/clinics/by-slug/${encodeURIComponent(slug)}`)
  ).json()
}

export async function clinicDoctors(
  tenantId: string,
  cursor: string | null = null,
): Promise<CursorPage<Doctor>> {
  const query = new URLSearchParams({ limit: '25' })
  if (cursor) query.set('cursor', cursor)
  return (
    await clinicRequest(
      `/clinics/${encodeURIComponent(tenantId)}/doctors?${query}`,
    )
  ).json()
}
