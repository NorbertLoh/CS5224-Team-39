import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { ErrorState } from '@/components/ErrorState'
import { LoadingState } from '@/components/LoadingState'
import { getAdminClinic } from './api'
import type { AdminClinic } from './api'
import { ClinicActions } from './ClinicActions'
import { refreshClinicViews } from '../clinics/cache'

export function ClinicManagement({ token, tenantId }: { token: string; tenantId: string }) {
  const client = useQueryClient()
  const [saving, setSaving] = useState(false)
  const queryKey = ['platform-clinic', token, tenantId]
  const clinic = useQuery({ queryKey, queryFn: ({ signal }) => getAdminClinic(tenantId, signal) })

  async function update(action: () => Promise<AdminClinic>) {
    setSaving(true)
    try {
      const saved = await action()
      client.setQueryData(queryKey, saved)
      await Promise.all([
        refreshClinicViews(client),
        client.invalidateQueries({ queryKey: ['clinic-doctors', tenantId] }),
      ])
    } finally { setSaving(false) }
  }

  if (clinic.isPending) return <LoadingState message="Loading clinic..." />
  if (clinic.isError) return <ErrorState message="Could not load this clinic. It may be unavailable, or your access has changed." onRetry={() => void clinic.refetch()} />
  return <section className="mt-8" aria-label="Manage selected clinic">
    <ClinicActions key={tenantId} clinic={clinic.data} disabled={saving || clinic.isFetching} update={update} />
  </section>
}
