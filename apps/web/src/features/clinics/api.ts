import { apiFetch } from '@/lib/api'
import { authConfig, readSession, refreshSession } from '@/auth/session'
import type { CursorPage } from '@/lib/api-types'
import type { ClinicProfile } from '../clinic-profile/profile'

export type Clinic = ClinicProfile & {
  tenant_id: string
  slug: string
  status: 'pending_review' | 'active' | 'rejected' | 'suspended'
}
export type Doctor = { doctor_id: string; display_name: string }
export type Identity = {
  subject_id: string
  global_roles: string[]
  memberships: Array<{ tenant_id: string; roles: string[]; status: string }>
}

export async function accessToken() {
  let session = readSession()
  if (!session) throw new Error('Sign in to manage your clinic.')
  if (session.expiresAt - Date.now() < 60000) {
    const config = authConfig()
    if (!config) throw new Error('Sign-in is not configured.')
    session = await refreshSession(config, session)
  }
  return session.accessToken
}

export async function clinicRequest(path: string, options: RequestInit = {}, authenticated = false) {
  return apiFetch(`/tenant${path}`, { ...options, accessToken: authenticated ? await accessToken() : undefined })
}

export async function listClinics(cursor: string | null = null, admin = false): Promise<CursorPage<Clinic>> {
  const query = new URLSearchParams({ limit: '25' })
  if (cursor) query.set('cursor', cursor)
  return (await clinicRequest(`${admin ? '/admin' : ''}/clinics?${query}`, {}, admin)).json()
}

export async function publicClinic(slug: string): Promise<Clinic> {
  return (await clinicRequest(`/clinics/by-slug/${encodeURIComponent(slug)}`)).json()
}

export async function clinicDoctors(tenantId: string, cursor: string | null = null): Promise<CursorPage<Doctor>> {
  const query = new URLSearchParams({ limit: '25' })
  if (cursor) query.set('cursor', cursor)
  return (await clinicRequest(`/clinics/${encodeURIComponent(tenantId)}/doctors?${query}`)).json()
}

export async function currentIdentity(): Promise<Identity> {
  return (await apiFetch('/identity/me', { accessToken: await accessToken() })).json()
}
