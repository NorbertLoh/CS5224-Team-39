import type { Payment } from './api'
import { consultationPrice } from '../../lib/money'
import { paymentTime, purposeLabels, statusLabels } from './model'
import { PaymentDetails } from './PaymentDetails'

export function PaymentHistory({ payments }: { payments: Payment[] }) {
  if (!payments.length)
    return (
      <p role="status" className="rounded-xl border p-6">
        No payments match these filters.
      </p>
    )
  return (
    <div className="overflow-x-auto rounded-xl border">
      <table className="w-full text-left text-sm">
        <caption className="px-4 py-3 text-left text-slate-600">
          {payments.length} payments · newest first · all amounts in SGD
        </caption>
        <thead className="bg-slate-50">
          <tr>
            {[
              'Created (Singapore)',
              'Purpose',
              'Status',
              'Amount',
              'Details',
            ].map((label) => (
              <th scope="col" key={label} className="px-4 py-3 font-medium">
                {label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {payments.map((payment) => (
            <tr key={payment.payment_id} className="border-t align-top">
              <td className="whitespace-nowrap px-4 py-4">
                {paymentTime(payment.created_at)}
              </td>
              <td className="px-4 py-4">
                {purposeLabels[payment.purpose] ?? payment.purpose}
              </td>
              <td className="px-4 py-4">
                <span className="inline-block rounded-md bg-slate-100 px-2 py-1">
                  {statusLabels[payment.status] ?? payment.status}
                </span>
                {payment.resolution === 'refund_required' && (
                  <span className="mt-2 block text-amber-800">
                    Refund review required
                  </span>
                )}
              </td>
              <td className="whitespace-nowrap px-4 py-4 font-medium">
                {consultationPrice(
                  payment.amount.amount_minor,
                  payment.amount.currency,
                )}
              </td>
              <td className="px-4 py-4">
                <PaymentDetails payment={payment} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
