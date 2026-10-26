import { useQuery } from '@tanstack/react-query'
import { readPrescription, recordsError } from './api'
import { PrescriptionDetails } from './PrescriptionDetails'
import { ErrorState } from '../../components/ErrorState'
import { LoadingState } from '../../components/LoadingState'

export function PatientPrescriptionDetail({
  id,
  token,
  subjectId,
}: {
  id: string
  token: string
  subjectId: string
}) {
  const query = useQuery({
    queryKey: ['records', 'prescription', token, id],
    queryFn: ({ signal }) => readPrescription(id, signal),
    retry: false,
    gcTime: 0,
  })
  if (query.isError)
    return (
      <ErrorState
        message={recordsError(query.error)}
        onRetry={() => void query.refetch()}
      />
    )
  if (!query.data || query.isFetching)
    return <LoadingState message="Loading prescription details..." />
  if (query.data.patient_id !== subjectId || query.data.prescription_id !== id)
    return (
      <ErrorState message="This prescription is unavailable to your account." />
    )
  return <PrescriptionDetails prescription={query.data} compact />
}
