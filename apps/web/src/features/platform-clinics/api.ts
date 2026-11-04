import type { Clinic } from '@/features/clinics/api'
import { clinicRequest } from '@/features/clinics/api'
import type { CursorPage } from '@/lib/api-types'
import { appendFilters, emptyFilters } from '@/lib/list-filters'
import type { ListFilterValues } from '@/lib/list-filters'

export type AdminClinic = Clinic & {
  commission_bps: number
  review_reason: string | null
}
export type ReviewDecision = 'approve' | 'reject' | 'suspend'
export const clinicStatuses = {
  pending_review: 'Pending review',
  active: 'Active',
  rejected: 'Rejected',
  suspended: 'Suspended',
}

export async function getAdminClinic(
  tenantId: string,
  signal?: AbortSignal,
): Promise<AdminClinic> {
  return (
    await clinicRequest(
      `/clinics/${encodeURIComponent(tenantId)}`,
      { signal },
      true,
    )
  ).json()
}

export async function listAdminClinics(
  status: string,
  cursor: string | null,
  signal?: AbortSignal,
  filters: ListFilterValues = emptyFilters,
): Promise<CursorPage<AdminClinic>> {
  const query = new URLSearchParams({ limit: '25' })
  if (status) query.set('status', status)
  if (cursor) query.set('cursor', cursor)
  appendFilters(query, filters)
  return (
    await clinicRequest(`/admin/clinics?${query}`, { signal }, true)
  ).json()
}

export async function clinicCounts(
  filters: ListFilterValues,
  signal?: AbortSignal,
): Promise<Record<keyof typeof clinicStatuses | 'total', number>> {
  const params = appendFilters(new URLSearchParams(), filters)
  return (
    await clinicRequest(`/admin/clinic-counts?${params}`, { signal }, true)
  ).json()
}

export async function reviewClinic(
  tenantId: string,
  decision: ReviewDecision,
  reason: string,
): Promise<AdminClinic> {
  return (
    await clinicRequest(
      `/clinics/${encodeURIComponent(tenantId)}/review`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          decision,
          reason: decision === 'approve' ? null : reason.trim(),
        }),
      },
      true,
    )
  ).json()
}

export async function saveCommission(
  tenantId: string,
  commissionBps: number,
): Promise<AdminClinic> {
  return (
    await clinicRequest(
      `/clinics/${encodeURIComponent(tenantId)}/commission`,
      {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ commission_bps: commissionBps }),
      },
      true,
    )
  ).json()
}
