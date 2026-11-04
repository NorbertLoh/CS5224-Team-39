import { ErrorState } from '@/components/ErrorState'
import { LoadingState } from '@/components/LoadingState'
import { DoctorTimetable } from '@/features/availability/DoctorTimetable'
import { useSchedulingIdentity } from '@/features/scheduling/useSchedulingIdentity'

export function AvailabilityEditor({
  tenantId: routeClinic,
}: {
  tenantId?: string
}) {
  const identity = useSchedulingIdentity()
  const memberships =
    identity.data?.memberships.filter(
      (member) => member.status === 'active' && member.roles.includes('doctor'),
    ) ?? []
  const tenantId = routeClinic ?? memberships[0]?.tenant_id
  if (identity.isError)
    return (
      <ErrorState
        message="Could not verify your doctor memberships."
        onRetry={() => void identity.refetch()}
      />
    )
  if (!identity.data)
    return <LoadingState message="Loading doctor memberships..." />
  if (!tenantId || !memberships.some((member) => member.tenant_id === tenantId))
    return <p role="status">No active doctor memberships.</p>
  return (
    <section className="mt-8 space-y-5" aria-labelledby="availability-heading">
      <h2 id="availability-heading" className="text-2xl font-semibold">
        Your availability
      </h2>
      <p className="text-slate-600">
        Select times to add or remove your availability. All times are Singapore
        time (SGT).
      </p>
      <DoctorTimetable
        key={`${identity.token}:${identity.data.subject_id}:${tenantId}`}
        tenantId={tenantId}
        doctorId={identity.data.subject_id}
        token={identity.token}
      />
    </section>
  )
}
