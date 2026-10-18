import { consultationPrice } from '../../lib/money'
import type { commissionTotals } from './model'

export function CommissionSummary({
  totals,
}: {
  totals: ReturnType<typeof commissionTotals>
}) {
  const cards = [
    ['Eligible payments', String(totals.count)],
    ['Payment total', consultationPrice(totals.amount, 'SGD')],
    ['Platform commission', consultationPrice(totals.commission, 'SGD')],
    ['Clinic gross portion', consultationPrice(totals.clinic, 'SGD')],
  ]
  return (
    <section aria-labelledby="commission-heading">
      <h2 id="commission-heading" className="text-xl font-semibold">
        Commission summary
      </h2>
      <dl className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {cards.map(([label, value]) => (
          <div key={label} className="rounded-xl border bg-white p-5">
            <dt className="text-sm text-slate-600">{label}</dt>
            <dd className="mt-2 text-2xl font-semibold">{value}</dd>
          </div>
        ))}
      </dl>
      <p className="mt-3 text-sm leading-relaxed text-slate-600">
        All dates, for the selected payment purpose. Only succeeded payments
        without a refund requirement are included; the history status filter
        does not change these totals. Amounts use the commission recorded on
        each payment. The clinic gross portion includes delivery costs and is
        before provider fees; it is not a net payout. Delivery fees are excluded
        from commission.
      </p>
    </section>
  )
}
