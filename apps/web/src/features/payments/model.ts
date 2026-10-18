import type { Payment } from './fixtures'

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
export const paymentStatuses = Object.keys(statusLabels)

export function clinicPayments(
  payments: Payment[],
  tenantId: string,
  purpose = 'all',
  status = 'all',
) {
  return payments
    .filter(
      (payment) =>
        payment.tenant_id === tenantId &&
        (purpose === 'all' || payment.purpose === purpose) &&
        (status === 'all' ||
          (status === 'refund_required'
            ? payment.resolution === 'refund_required'
            : payment.status === status)),
    )
    .sort(
      (a, b) =>
        a.created_at.localeCompare(b.created_at) ||
        a.payment_id.localeCompare(b.payment_id),
    )
}

export function commissionTotals(
  payments: Payment[],
  tenantId: string,
  purpose = 'all',
) {
  const totals = { count: 0, amount: 0, commission: 0, clinic: 0 }
  for (const payment of clinicPayments(payments, tenantId, purpose)) {
    if (payment.status !== 'succeeded' || payment.resolution !== 'none')
      continue
    const amounts = [
      payment.amount,
      payment.commission_amount,
      payment.clinic_amount,
    ]
    if (
      amounts.some(
        (money) =>
          money.currency !== 'SGD' ||
          !Number.isSafeInteger(money.amount_minor) ||
          money.amount_minor < 0,
      )
    ) {
      throw new Error('Payment totals are unavailable for invalid amounts.')
    }
    totals.count += 1
    totals.amount += payment.amount.amount_minor
    totals.commission += payment.commission_amount.amount_minor
    totals.clinic += payment.clinic_amount.amount_minor
    if (
      ![totals.amount, totals.commission, totals.clinic].every(
        Number.isSafeInteger,
      )
    ) {
      throw new Error('Payment totals exceed the supported range.')
    }
  }
  return totals
}

export function paymentTime(instant: string) {
  return (
    new Date(instant).toLocaleString('en-SG', { timeZone: 'Asia/Singapore' }) +
    ' SGT'
  )
}
