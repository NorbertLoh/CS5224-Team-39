export type DocumentMetadata = {
  document_id: string
  tenant_id: string
  appointment_id: string
  prescription_id: string | null
  payment_id: string | null
  medical_certificate_id: string | null
  kind: 'prescription_pdf' | 'receipt_pdf' | 'medical_certificate_pdf'
  status: 'pending' | 'ready' | 'failed'
  created_at: string
  updated_at: string
}

export const documentNames: Record<DocumentMetadata['kind'], string> = {
  prescription_pdf: 'Prescription',
  receipt_pdf: 'Receipt',
  medical_certificate_pdf: 'Medical certificate',
}

export const documentStates: Record<DocumentMetadata['status'], string> = {
  pending: 'Preparing PDF',
  ready: 'Ready to download',
  failed: 'PDF unavailable',
}

export function documentDate(instant: string) {
  return new Intl.DateTimeFormat('en-SG', {
    timeZone: 'Asia/Singapore', day: 'numeric', month: 'short', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
  }).format(new Date(instant))
}
