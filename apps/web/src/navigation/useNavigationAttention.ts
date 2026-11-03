import { readSession } from '@/auth/session'
import type { Identity } from '@/auth/identity'
import {
  myApplication,
  applicationCounts,
} from '@/features/doctor-onboarding/api'
import { clinicCounts } from '@/features/platform-clinics/api'
import { listAppointments } from '@/features/scheduling/api'
import { request } from '@/features/fulfilment/api/client'
import type { Order } from '@/features/fulfilment/api'
import type { CursorPage } from '@/lib/api-types'
import { emptyFilters } from '@/lib/list-filters'
import {
  appointmentPaymentAttention,
  orderAttention,
  pendingAttention,
  verificationAttention,
} from './attention'
import { useQuery } from '@tanstack/react-query'

const refresh = {
  staleTime: 15000,
  refetchInterval: 30000,
  retry: false,
} as const

/** Follow every page; never mistake the first page's size for a full count. */
export async function navigationItems<T>(
  load: (cursor: string | null) => Promise<CursorPage<T>>,
) {
  const items: T[] = []
  const seen = new Set<string>()
  let cursor: string | null = null
  do {
    const page = await load(cursor)
    items.push(...page.items)
    cursor = page.next_cursor
    if (cursor && seen.has(cursor))
      throw new Error('Navigation status pagination did not advance.')
    if (cursor) seen.add(cursor)
  } while (cursor)
  return items
}

export function useVerificationAttention() {
  const query = useQuery({
    queryKey: ['doctor-application', readSession()?.accessToken],
    queryFn: ({ signal }) => myApplication(signal),
    ...refresh,
  })
  return query.isSuccess ? verificationAttention(query.data) : undefined
}

export function usePlatformAttention() {
  const token = readSession()?.accessToken
  const clinics = useQuery({
    queryKey: ['platform-clinics', 'counts', token, emptyFilters],
    queryFn: ({ signal }) => clinicCounts(emptyFilters, signal),
    ...refresh,
  })
  const doctors = useQuery({
    queryKey: ['doctor-applications', 'counts', token, emptyFilters],
    queryFn: ({ signal }) => applicationCounts(signal),
    ...refresh,
  })
  return {
    clinics: clinics.isSuccess
      ? pendingAttention(
          clinics.data.pending_review,
          'Clinic applications awaiting your review.',
        )
      : undefined,
    doctors: doctors.isSuccess
      ? pendingAttention(
          doctors.data.pending,
          'Doctor applications awaiting your review.',
        )
      : undefined,
  }
}

export function usePatientAttention(identity: Identity) {
  const token = readSession()?.accessToken
  const subject = identity.subject_id
  const appointments = useQuery({
    queryKey: ['scheduling', 'navigation-attention', token, subject],
    queryFn: ({ signal }) =>
      navigationItems((cursor) =>
        listAppointments(
          undefined,
          cursor,
          signal,
          'upcoming',
          emptyFilters,
          'patient',
        ),
      ),
    ...refresh,
  })
  const orders = useQuery({
    queryKey: ['fulfilment', 'navigation-attention', token, subject],
    queryFn: ({ signal }) =>
      navigationItems<Order>(async (cursor) => {
        const params = new URLSearchParams({ limit: '100', sort: 'newest' })
        if (cursor) params.set('cursor', cursor)
        // Read the lightweight list, without one delivery-detail request per order.
        return (await request(`/orders?${params}`, { signal })).json()
      }),
    ...refresh,
  })
  return {
    appointments: appointments.isSuccess
      ? appointmentPaymentAttention(appointments.data, subject)
      : undefined,
    orders: orders.isSuccess ? orderAttention(orders.data, subject) : undefined,
  }
}
