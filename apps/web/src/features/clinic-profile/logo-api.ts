import { readSession } from '@/auth/session'
import { apiFetch } from '@/lib/api'
import type { ClinicProfile } from './profile'

export const profileApiEnabled = import.meta.env?.VITE_CLINIC_PROFILE_API_ENABLED === 'true'
export const maxLogoBytes = 2 * 1024 * 1024

export function validateLogoFile(file: File): string | undefined {
  if (!['image/png', 'image/jpeg', 'image/webp'].includes(file.type)) return 'Choose a PNG, JPEG or WebP image.'
  if (!file.size || file.size > maxLogoBytes) return 'Choose an image up to 2 MB.'
}

async function request(tenantId: string, options: RequestInit = {}, suffix = '/logo') {
  const session = readSession()
  if (!session || session.expiresAt <= Date.now()) throw new Error('Sign in from the home page, then return to upload your logo.')
  return apiFetch(`/tenant/clinics/${encodeURIComponent(tenantId)}${suffix}`, {
    ...options, accessToken: session.accessToken,
  })
}

export async function readLogo(tenantId: string) {
  const response = await request(tenantId, {}, '')
  const profile = await response.json()
  return logoResult(tenantId, profile.branding.logo_url)
}

async function logoResult(tenantId: string, url: string | null) {
  if (!url) return { url: null, preview: null }
  // Authenticated image reads support local private S3; public CDN serves production logos.
  try {
    const response = await request(tenantId)
    return { url, preview: URL.createObjectURL(await response.blob()) }
  } catch {
    return { url, preview: url }
  }
}

export async function uploadLogo(tenantId: string, file: File) {
  const response = await request(tenantId, { method: 'PUT', body: file, headers: { 'Content-Type': file.type } })
  const profile = await response.json()
  return logoResult(tenantId, profile.branding.logo_url)
}

export async function removeLogo(tenantId: string) {
  await request(tenantId, { method: 'DELETE' })
}

export type EditableClinic = ClinicProfile & { slug: string; tenant_id: string }

export async function readClinic(tenantId: string): Promise<EditableClinic> {
  const response = await request(tenantId, {}, '')
  return response.json()
}

export async function saveClinic(tenantId: string, profile: ClinicProfile): Promise<EditableClinic> {
  const response = await request(tenantId, {
    method: 'PATCH', body: JSON.stringify(profile), headers: { 'Content-Type': 'application/json' },
  }, '')
  return response.json()
}
