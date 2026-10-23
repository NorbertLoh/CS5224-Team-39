import { useQuery } from '@tanstack/react-query'
import { paymentDetail } from '../payments/api'
import { documentNames } from './types'
import type { DocumentMetadata } from './types'

export function useDocumentName(item: DocumentMetadata, token: string) {
  const payment = useQuery({
    queryKey: ['documents', 'receipt-payment', token, item.payment_id],
    queryFn: ({ signal }) => paymentDetail(item.payment_id!, signal),
    enabled: item.kind === 'receipt_pdf' && !!item.payment_id,
    staleTime: 60000,
    retry: false,
  })
  if (
    item.kind !== 'receipt_pdf' ||
    payment.data?.payment_id !== item.payment_id ||
    payment.data?.tenant_id !== item.tenant_id
  )
    return documentNames[item.kind]

  switch (payment.data.purpose) {
    case 'consultation':
      return 'Consultation receipt'
    case 'medication_delivery':
      return 'Medicines & delivery receipt'
    default:
      return documentNames[item.kind]
  }
}
