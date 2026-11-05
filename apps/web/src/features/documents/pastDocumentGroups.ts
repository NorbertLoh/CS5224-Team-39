import type { DocumentMetadata } from '@/features/documents/types'
import type { Appointment } from '@/features/scheduling/api'

export const documentKindOrder = [
  'prescription_pdf',
  'receipt_pdf',
  'medical_certificate_pdf',
] as const

export function pastDocumentGroups(
  documents: DocumentMetadata[],
  visits: Appointment[],
) {
  const groups = new Map<
    string,
    { visit: Appointment; documents: DocumentMetadata[] }
  >()
  for (const visit of visits) {
    const key = `${visit.tenant_id}:${visit.appointment_id}`
    if (!groups.has(key)) groups.set(key, { visit, documents: [] })
  }
  for (const document of documents) {
    const group = groups.get(`${document.tenant_id}:${document.appointment_id}`)
    if (
      group &&
      !group.documents.some((item) => item.document_id === document.document_id)
    ) {
      group.documents.push(document)
    }
  }
  return [...groups.values()]
    .filter((group) => group.documents.length > 0)
    .map((group) => ({
      ...group,
      documents: group.documents.sort(
        (a, b) =>
          documentKindOrder.indexOf(a.kind) -
            documentKindOrder.indexOf(b.kind) ||
          Date.parse(b.created_at) - Date.parse(a.created_at) ||
          a.document_id.localeCompare(b.document_id),
      ),
    }))
    .sort(
      (a, b) =>
        Date.parse(b.visit.starts_at) - Date.parse(a.visit.starts_at) ||
        a.visit.appointment_id.localeCompare(b.visit.appointment_id),
    )
}
