import { useSchedulingIdentity } from '../scheduling/useSchedulingIdentity'
import { ErrorState } from '../../components/ErrorState'
import { LoadingState } from '../../components/LoadingState'
import { PatientPrescriptionList } from './PatientPrescriptionList'

export function PatientPrescriptions() {
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
    />
  )
}
