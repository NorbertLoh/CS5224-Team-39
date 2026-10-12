import { QueryClient } from '@tanstack/react-query'
import { ApiError } from './api-client'
import type { ApiService } from './api-types'

export interface QueryScope {
  subject: string | null
  tenantId: string | null
  role?: string
}

export function apiQueryKey(scope: QueryScope, service: ApiService, resource: string, params: Record<string, unknown> = {}) {
  return ['api', { ...scope }, service, resource, { ...params }] as const
}

export function shouldRetryQuery(failureCount: number, error: unknown): boolean {
  if (failureCount >= 2 || !(error instanceof ApiError) || error.method !== 'GET') return false
  if (error.retryAfterMs !== undefined && error.retryAfterMs > 30_000) return false
  return error.kind === 'network'
    || (error.kind === 'http' && [429, 500, 502, 503, 504].includes(error.status ?? 0))
}

export function queryRetryDelay(attempt: number, error: unknown): number {
  return error instanceof ApiError && error.retryAfterMs !== undefined
    ? Math.min(error.retryAfterMs, 30_000)
    : Math.min(1000 * 2 ** attempt, 30_000)
}

export function createQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        gcTime: 5 * 60_000,
        refetchOnWindowFocus: false,
        retry: shouldRetryQuery,
        retryDelay: queryRetryDelay,
      },
      mutations: { retry: false },
    },
  })
}

export const queryClient = createQueryClient()
