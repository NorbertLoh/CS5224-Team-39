import { useQuery } from '@tanstack/react-query'
import { readSession } from '@/auth/session'
import { ErrorState } from '@/components/ErrorState'
import { readClinic } from '../clinic-profile/logo-api'

export function ClinicContext({ tenantId }: { tenantId: string }) {
  const clinic = useQuery({
    queryKey: ['clinic-profile', readSession()?.accessToken, tenantId],
    queryFn: () => readClinic(tenantId),
  })

  return <div className="mt-3">
    <p role="status" className="break-words text-lg font-medium text-slate-600">
      {clinic.data ? `Clinic: ${clinic.data.name}` : clinic.isPending ? 'Loading clinic name...' : `Clinic: ${tenantId}`}
    </p>
    {clinic.isError && <ErrorState message="Could not load the clinic name." onRetry={() => void clinic.refetch()} />}
  </div>
}
