import { DocumentList } from '@/features/documents/DocumentList'
import { PatientPrescriptions } from '@/features/records/patient/PatientPrescriptions'

export function PatientRecordsPage({
  page,
}: {
  page: 'prescriptions' | 'documents'
}) {
  return (
    <main className="mx-auto max-w-6xl px-6 py-10">
      {page === 'prescriptions' ? (
        <PatientPrescriptions headingLevel={1} />
      ) : (
        <DocumentList role="patient" headingLevel={1} />
      )}
    </main>
  )
}
