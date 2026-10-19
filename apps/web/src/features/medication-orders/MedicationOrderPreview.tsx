import { useState } from 'react'
import { OrderFlow } from './OrderFlow'

const scenarios = {
  issued: 'Issued prescription',
  empty: 'No prescriptions',
  draft: 'Draft prescription',
  voided: 'Voided prescription',
  loading: 'Loading orders',
  error: 'Orders unavailable',
}
type Scenario = keyof typeof scenarios

export function MedicationOrderPreview() {
  const [scenario, setScenario] = useState<Scenario>('issued')
  return (
    <main className="mx-auto max-w-4xl space-y-6 px-4 py-8 sm:px-6">
      <a href="/patient" className="text-sm underline">
        Back to patient dashboard
      </a>
      <div>
        <h1 className="text-3xl font-semibold">Medication and delivery</h1>
        <p className="mt-2 text-slate-600">
          Review your order, delivery quote and payment.
        </p>
      </div>
      <aside className="space-y-3 rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm">
        <p className="font-semibold">
          Medication order preview · synthetic data
        </p>
        <p>
          No payment is taken and no order or delivery is created. This preview
          uses historical contract examples. Addresses stay in this page’s
          memory; use demo details.
        </p>
        <label className="block font-medium">
          Order scenario
          <select
            className="mt-1 block w-full rounded border bg-white p-2"
            value={scenario}
            onChange={(event) => setScenario(event.target.value as Scenario)}
          >
            {Object.entries(scenarios).map(([key, label]) => (
              <option key={key} value={key}>
                {label}
              </option>
            ))}
          </select>
        </label>
      </aside>
      {scenario === 'issued' ? (
        <OrderFlow key={scenario} />
      ) : (
        <section className="rounded-xl border p-5">
          {scenario === 'loading' && (
            <p role="status" aria-busy="true">
              Loading medication orders...
            </p>
          )}
          {scenario === 'empty' && (
            <p role="status">
              No issued prescriptions available. Your doctor must issue a
              prescription before you can order medication.
            </p>
          )}
          {(scenario === 'draft' || scenario === 'voided') && (
            <p role="status">
              This prescription is {scenario} and cannot be used to create an
              order.
            </p>
          )}
          {scenario === 'error' && (
            <div role="alert">
              <p>Medication orders could not be loaded.</p>
              <button
                className="mt-3 rounded border px-4 py-2"
                onClick={() => setScenario('issued')}
              >
                Retry demo orders
              </button>
            </div>
          )}
        </section>
      )}
    </main>
  )
}
