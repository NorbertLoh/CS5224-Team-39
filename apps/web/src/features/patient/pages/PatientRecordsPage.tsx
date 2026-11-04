import { DocumentList } from '@/features/documents/DocumentList'
import { PatientPrescriptions } from '@/features/records/patient/PatientPrescriptions'

export function PatientRecordsPage({
  page,
}: {
  page: 'prescriptions' | 'documents'
}) {
  return (
    <main className="mx-auto max-w-5xl px-4 py-8 sm:px-6">
      {page === 'prescriptions' ? (
        <PatientPrescriptions headingLevel={1} />
      ) : (
        <DocumentList role="patient" headingLevel={1} />
      )}
    </main>
  )
}
