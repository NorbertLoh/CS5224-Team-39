import { useQuery } from '@tanstack/react-query'
import { currentIdentity } from './api'
import { readClinic } from '../clinic-profile/logo-api'
import { ClinicDirectory, ClinicLinks } from './ClinicDirectory'
import { ErrorState } from '@/components/ErrorState'
import { LoadingState } from '@/components/LoadingState'
import type { Session } from '@/auth/session'

export function ManagedClinics({ session }: { session: Session }) {
  const identity = useQuery({ queryKey: ['identity', session.accessToken], queryFn: currentIdentity })
  const ids = identity.data?.memberships
    .filter(item => item.status === 'active' && item.roles.includes('clinic_admin'))
    .map(item => item.tenant_id) ?? []
  const platform = identity.data?.global_roles.includes('platform_admin')
  const clinics = useQuery({
    queryKey: ['managed-clinics', session.accessToken, ids],
    queryFn: () => Promise.all(ids.map(readClinic)),
    enabled: Boolean(identity.data && !platform),
  })
  if (identity.isPending) return <LoadingState message="Loading your access..." />
  if (identity.isError) return <ErrorState message="Could not load your access." onRetry={() => void identity.refetch()} />
  if (!platform && !ids.length) return null

  let content
  if (platform) content = <><a href="/platform-admin/clinics" className="mt-5 inline-block font-medium underline">Clinic approval and commission</a><ClinicDirectory admin /></>
  else if (clinics.isPending) content = <LoadingState message="Loading your clinics..." />
  else if (clinics.isError) content = <ErrorState message="Could not load your clinics." onRetry={() => void clinics.refetch()} />
  else content = <ClinicLinks clinics={clinics.data} edit />

  return <section className="mt-10"><h2 className="text-2xl font-semibold">Manage clinics</h2>{content}</section>
}
