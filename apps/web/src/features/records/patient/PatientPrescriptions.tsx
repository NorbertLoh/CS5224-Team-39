import { ErrorState } from '@/components/ErrorState'
import { LoadingState } from '@/components/LoadingState'
import { PatientPrescriptionList } from '@/features/records/patient/PatientPrescriptionList'
import { useSchedulingIdentity } from '@/features/scheduling/useSchedulingIdentity'

export function PatientPrescriptions({
  headingLevel = 2,
}: {
  headingLevel?: 1 | 2
}) {
  const identity = useSchedulingIdentity()
  if (identity.isError)
    return (
      <ErrorState
        message="Could not verify prescription access."
        onRetry={() => void identity.refetch()}
      />
    )
  if (!identity.data || !identity.token)
    return <LoadingState message="Loading prescription access..." />
  return (
    <PatientPrescriptionList
      key={identity.token}
      token={identity.token}
      subjectId={identity.data.subject_id}
      headingLevel={headingLevel}
    />
  )
}
