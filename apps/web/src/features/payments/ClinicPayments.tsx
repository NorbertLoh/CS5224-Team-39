import { useState } from 'react'
import { fixtureClinics, paymentFixtures } from './fixtures'
import {
  clinicPayments,
  commissionTotals,
  purposeLabels,
  statusLabels,
} from './model'
import { CommissionSummary } from './CommissionSummary'
import { PaymentHistory } from './PaymentHistory'
import { PaymentFilter } from './PaymentFilter'
import { ClinicPaymentNavigation } from './ClinicPaymentNavigation'

export function ClinicPayments({ tenantId }: { tenantId: string }) {
  const [purpose, setPurpose] = useState('all')
  const [status, setStatus] = useState('all')
  const clinic = fixtureClinics.find((item) => item.tenant_id === tenantId)
  const payments = clinicPayments(paymentFixtures, tenantId, purpose, status)
  const totals = commissionTotals(paymentFixtures, tenantId, purpose)
  return (
    <main className="mx-auto max-w-6xl space-y-8 px-4 py-8 sm:px-6">
      <ClinicPaymentNavigation tenantId={tenantId} />
      <header>
        <p className="text-sm text-slate-600">
          {clinic?.name ?? 'Selected clinic'}
        </p>
        <h1 className="mt-2 text-3xl font-semibold">Payments and commission</h1>
        <p className="mt-3 rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm">
          Fixture preview · synthetic payment history. No live charges, refunds
          or payouts are shown or changed here. Real billing integration follows
          in B07.
        </p>
      </header>
      <PaymentFilter
        label="Payment purpose"
        value={purpose}
        onChange={setPurpose}
        options={{ all: 'All purposes', ...purposeLabels }}
      />
      <CommissionSummary totals={totals} />
      <section className="space-y-4" aria-labelledby="payment-history-heading">
        <h2 id="payment-history-heading" className="text-xl font-semibold">
          Payment history
        </h2>
        <PaymentFilter
          label="History status"
          value={status}
          onChange={setStatus}
          options={{
            all: 'All statuses',
            ...statusLabels,
            refund_required: 'Refund review required',
          }}
        />
        <PaymentHistory payments={payments} />
      </section>
    </main>
  )
}
