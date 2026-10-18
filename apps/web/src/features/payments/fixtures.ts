import shared from '../../../../../dev/fixtures/telelink.json'

export type Payment = (typeof shared.payments)[number]

const original = shared.payments[0]
// Additional synthetic terminal states supplement the agreed shared fixtures.
const refundExamples: Payment[] = [
  'refund_pending',
  'refund_failed',
  'refunded',
].map((status, index) => ({
  ...original,
  payment_id: `00000000-0000-4000-8000-0000000002${index}0`,
  appointment_id: `00000000-0000-4000-8000-0000000002${index}1`,
    order_id: null,
    quote_id: null,
  status,
  resolution: status === 'refunded' ? 'none' : 'refund_required',
}))

export const paymentFixtures: Payment[] = [
  ...shared.payments,
  ...refundExamples,
]
export const fixtureClinics = shared.clinics
