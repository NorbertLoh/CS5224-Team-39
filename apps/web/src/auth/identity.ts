import { accessToken } from '@/auth/access-token'
import { apiFetch } from '@/lib/api'

export type Identity = {
  subject_id: string
  global_roles: string[]
  memberships: Array<{ tenant_id: string; roles: string[]; status: string }>
}

export async function currentIdentity(): Promise<Identity> {
  return (
    await apiFetch('/identity/me', { accessToken: await accessToken() })
  ).json()
}
