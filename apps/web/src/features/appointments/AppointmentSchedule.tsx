import { useState } from 'react'
import type { AppointmentRole } from './types'
import { useSchedulingIdentity } from '../scheduling/useSchedulingIdentity'
import { useClinicNames } from '../clinics/useClinicNames'
import { ErrorState } from '../../components/ErrorState'
import { LoadingState } from '../../components/LoadingState'
import { AppointmentPeriods } from './AppointmentPeriods'

export function AppointmentSchedule({
  role,
  tenantId,
}: {
  role: AppointmentRole
  tenantId?: string
}) {
  const identity = useSchedulingIdentity()
  const [selectedClinic, setSelectedClinic] = useState('')
  const memberships =
    identity.data?.memberships.filter(
      (member) => member.status === 'active' && member.roles.includes(role),
    ) ?? []
  const clinicName = useClinicNames(
    role === 'clinic_admin' && !tenantId
      ? memberships.map((member) => member.tenant_id)
      : [],
    true,
  )
  const clinic =
    tenantId ??
    (role === 'clinic_admin'
      ? memberships.some((member) => member.tenant_id === selectedClinic)
        ? selectedClinic
        : memberships[0]?.tenant_id
      : undefined)
  if (identity.isError)
    return (
      <ErrorState
        message="Could not verify appointment access."
        onRetry={() => void identity.refetch()}
      />
    )
  if (!identity.data)
    return <LoadingState message="Loading appointment access..." />
  if (
    role === 'clinic_admin' &&
    !memberships.some((member) => member.tenant_id === clinic)
  )
    return (
      <p role="status">No active clinic admin membership for this clinic.</p>
    )
  return (
    <section aria-labelledby="appointments-heading" className="mt-8 space-y-5">
      <h2 id="appointments-heading" className="text-2xl font-semibold">
        Appointments
      </h2>
      <p className="text-slate-600">
        Select an appointment to see its details. All dates and times are
        Singapore time (SGT).
      </p>
      {role === 'clinic_admin' && !tenantId && (
        <label className="flex max-w-sm flex-col gap-2">
          Clinic
          <select
            className="rounded border bg-white p-2"
            value={clinic}
            onChange={(event) => setSelectedClinic(event.target.value)}
          >
            {memberships.map((member) => (
              <option key={member.tenant_id} value={member.tenant_id}>
                {clinicName(member.tenant_id)}
              </option>
            ))}
          </select>
        </label>
      )}
      <AppointmentPeriods
        key={`${identity.token}:${role}:${clinic ?? ''}`}
        role={role}
        tenantId={clinic}
        subjectId={identity.data.subject_id}
        token={identity.token}
      />
    </section>
  )
}
