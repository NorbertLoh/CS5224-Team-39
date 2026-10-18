import { useState } from 'react'
import { fixtureClinics, paymentFixtures } from './fixtures'
import {
  clinicPayments,
  commissionTotals,
  paymentStatuses,
  purposeLabels,
  statusLabels,
} from './model'
import { CommissionSummary } from './CommissionSummary'
import { PaymentHistory } from './PaymentHistory'

export function ClinicPayments({ tenantId }: { tenantId: string }) {
  const [purpose, setPurpose] = useState('all')
  const [status, setStatus] = useState('all')
  const clinic = fixtureClinics.find((item) => item.tenant_id === tenantId)
  const payments = clinicPayments(paymentFixtures, tenantId, purpose, status)
  const totals = commissionTotals(paymentFixtures, tenantId, purpose)
  return (
    <main className="mx-auto max-w-6xl space-y-8 px-4 py-8 sm:px-6">
      <nav
        aria-label="Clinic management"
        className="flex flex-wrap gap-5 text-sm underline"
      >
        <a href="/clinic-admin">Your clinics</a>
        <a href={`/clinic-admin/clinics/${tenantId}/profile`}>Clinic profile</a>
        <a href={`/clinic-admin/clinics/${tenantId}/staff`}>Staff</a>
        <a
          href={`/clinic-admin/clinics/${tenantId}/payments`}
          aria-current="page"
        >
          Payments
        </a>
      </nav>
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
      <label className="block max-w-sm text-sm font-medium">
        Payment purpose
        <select
          className="mt-2 block w-full rounded-lg border bg-white p-3"
          value={purpose}
          onChange={(event) => setPurpose(event.target.value)}
        >
          <option value="all">All purposes</option>
          {Object.entries(purposeLabels).map(([key, label]) => (
            <option key={key} value={key}>
              {label}
            </option>
          ))}
        </select>
      </label>
      <CommissionSummary totals={totals} />
      <section className="space-y-4" aria-labelledby="payment-history-heading">
        <h2 id="payment-history-heading" className="text-xl font-semibold">
          Payment history
        </h2>
        <label className="block max-w-sm text-sm font-medium">
          History status
          <select
            className="mt-2 block w-full rounded-lg border bg-white p-3"
            value={status}
            onChange={(event) => setStatus(event.target.value)}
          >
            <option value="all">All statuses</option>
            {paymentStatuses.map((key) => (
              <option key={key} value={key}>
                {statusLabels[key]}
              </option>
            ))}
            <option value="refund_required">Refund review required</option>
          </select>
        </label>
        <PaymentHistory payments={payments} />
      </section>
    </main>
  )
}
