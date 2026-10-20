import { useState } from 'react'
import { ErrorState } from '../../components/ErrorState'
import { LoadingState } from '../../components/LoadingState'
import { useSchedulingIdentity } from '../scheduling/useSchedulingIdentity'
import { DoctorTimetable } from './DoctorTimetable'
import { useClinicNames } from '../clinics/useClinicNames'

export function AvailabilityEditor({
  tenantId: routeClinic,
}: {
  tenantId?: string
}) {
  const identity = useSchedulingIdentity()
  const [selectedClinic, setSelectedClinic] = useState('')
  const memberships =
    identity.data?.memberships.filter(
      (member) => member.status === 'active' && member.roles.includes('doctor'),
    ) ?? []
  const clinicName = useClinicNames(
    memberships.map((member) => member.tenant_id),
  )
  const tenantId =
    routeClinic ??
    (memberships.some((member) => member.tenant_id === selectedClinic)
      ? selectedClinic
      : memberships[0]?.tenant_id)
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
      <label className="flex max-w-sm flex-col gap-2">
        Clinic
        <select
          className="rounded border bg-white p-2"
          value={tenantId}
          disabled={Boolean(routeClinic)}
          onChange={(event) => setSelectedClinic(event.target.value)}
        >
          {memberships.map((member) => (
            <option key={member.tenant_id} value={member.tenant_id}>
              {clinicName(member.tenant_id)}
            </option>
          ))}
        </select>
      </label>
      <DoctorTimetable
        key={`${identity.token}:${identity.data.subject_id}:${tenantId}`}
        tenantId={tenantId}
        doctorId={identity.data.subject_id}
        token={identity.token}
      />
    </section>
  )
}
