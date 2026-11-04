import { accessToken } from '@/auth/access-token'
import { apiFetch } from '@/lib/api'

export async function request(path: string, init: RequestInit = {}) {
  return apiFetch(`/fulfilment${path}`, {
    ...init,
    accessToken: await accessToken(),
    signal: init.signal ?? AbortSignal.timeout(20000),
  })
}
