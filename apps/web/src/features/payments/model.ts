export const purposeLabels: Record<string, string> = {
  consultation: 'Consultation',
  medication_delivery: 'Medication and delivery',
}
export const statusLabels: Record<string, string> = {
  pending: 'Pending',
  succeeded: 'Succeeded',
  failed: 'Failed',
  refund_pending: 'Refund processing',
  refund_failed: 'Refund failed',
  refunded: 'Refunded',
}

export function paymentTime(instant: string) {
  return (
    new Date(instant).toLocaleString('en-SG', { timeZone: 'Asia/Singapore' }) +
    ' SGT'
  )
}
