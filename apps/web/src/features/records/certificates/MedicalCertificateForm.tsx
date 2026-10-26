import { ErrorState } from '@/components/ErrorState'
import { LoadingState } from '@/components/LoadingState'
import { readMedicalCertificate, recordsError } from '@/features/records/api'
import { MedicalCertificateEditor } from '@/features/records/certificates/MedicalCertificateEditor'
import type { RecordFormStateChange } from '@/features/records/hooks/useRecordFormState'
import { useQuery } from '@tanstack/react-query'

export function MedicalCertificateForm({
  appointmentId,
  token,
  editable,
  onStateChange,
}: {
  appointmentId: string
  token: string
  editable: boolean
  onStateChange?: RecordFormStateChange
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
      onStateChange={onStateChange}
    />
  )
}
