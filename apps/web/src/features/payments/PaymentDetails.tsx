import type { Payment } from './fixtures'
import { consultationPrice } from '../../lib/money'
import { paymentTime } from './model'

export function PaymentDetails({ payment }: { payment: Payment }) {
  return (
    <details className="min-w-48">
      <summary className="cursor-pointer font-medium underline">
        Payment details
      </summary>
      <dl className="mt-3 space-y-3 text-sm">
        <div>
          <dt className="text-slate-500">Payment reference</dt>
          <dd className="break-all">{payment.payment_id}</dd>
        </div>
        <div>
          <dt className="text-slate-500">
            {payment.purpose === 'consultation'
              ? 'Appointment reference'
              : 'Order reference'}
          </dt>
          <dd className="break-all">
            {payment.appointment_id ?? payment.order_id}
          </dd>
        </div>
        <div>
          <dt className="text-slate-500">Commission rate at payment</dt>
          <dd>{payment.commission_bps / 100}%</dd>
        </div>
        <div>
          <dt className="text-slate-500">Platform commission snapshot</dt>
          <dd>
            {consultationPrice(
              payment.commission_amount.amount_minor,
              payment.commission_amount.currency,
            )}
          </dd>
        </div>
        <div>
          <dt className="text-slate-500">Clinic gross portion snapshot</dt>
          <dd>
            {consultationPrice(
              payment.clinic_amount.amount_minor,
              payment.clinic_amount.currency,
            )}
          </dd>
        </div>
        <div>
          <dt className="text-slate-500">Last updated</dt>
          <dd>{paymentTime(payment.updated_at)}</dd>
        </div>
      </dl>
      {payment.resolution === 'refund_required' && (
        <p className="mt-3 text-sm text-amber-800">
          Manual refund review required. Contact platform support with this
          payment reference. No refund is initiated here.
        </p>
      )}
    </details>
  )
}
