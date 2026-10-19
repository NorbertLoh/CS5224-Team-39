import { useQuery } from '@tanstack/react-query'
import { readMedicalCertificate, recordsError } from './api'
import { MedicalCertificateEditor } from './MedicalCertificateEditor'
import { ErrorState } from '../../components/ErrorState'
import { LoadingState } from '../../components/LoadingState'

export function MedicalCertificateForm({
  appointmentId,
  token,
  editable,
}: {
  appointmentId: string
  token: string
  editable: boolean
}) {
  const query = useQuery({
    queryKey: ['records', 'mc', token, appointmentId],
    queryFn: ({ signal }) => readMedicalCertificate(appointmentId, signal),
    retry: false,
    gcTime: 0,
    refetchOnWindowFocus: false,
  })
  if (query.isError)
    return (
      <ErrorState
        message={recordsError(query.error)}
        onRetry={() => void query.refetch()}
      />
    )
  if (query.isPending)
    return <LoadingState message="Loading medical certificate..." />
  return (
    <MedicalCertificateEditor
      key={appointmentId}
      appointmentId={appointmentId}
      draft={query.data}
      editable={editable}
    />
  )
}
