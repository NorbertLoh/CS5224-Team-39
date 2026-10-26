import { accessToken } from '@/auth/access-token'
import { apiFetch } from '@/lib/api'

export async function request(path: string, init: RequestInit = {}) {
  return apiFetch(path, {
    ...init,
    accessToken: await accessToken(),
    signal: init.signal
      ? AbortSignal.any([init.signal, AbortSignal.timeout(15000)])
      : AbortSignal.timeout(15000),
  })
}

export function json(method: string, body: unknown): RequestInit {
  return {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }
}

export const base = '/clinical-records'
export const id = encodeURIComponent
