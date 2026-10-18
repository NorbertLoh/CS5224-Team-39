import { useState } from 'react'
import { CheckoutStatus } from './CheckoutStatus'
import { checkoutSummary, fixtureNow, scenarios } from './fixtures'
import type { Scenario } from './fixtures'
import { checkoutState } from './status'

export function CheckoutPreview() {
  const [scenario, setScenario] = useState<Scenario>('return')
  const [checked, setChecked] = useState(false)
  const selected = scenarios[scenario]
  const state =
    scenario === 'missing'
      ? 'missing'
      : scenario === 'error'
        ? 'error'
        : scenario === 'return' && !checked
          ? 'return'
          : checkoutState(selected.snapshot!, fixtureNow)
  return (
    <main className="mx-auto max-w-2xl space-y-6 px-4 py-8 sm:px-6">
      <aside className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm">
        <p className="font-semibold">Checkout preview · synthetic data</p>
        <p className="mt-2">
          No payment is taken and no appointment is changed. These historical
          examples use a fixed server time. Open a booking from Appointments to view live billing.
        </p>
        <label className="mt-4 block">
          Preview scenario
          <select
            className="mt-1 block w-full rounded border bg-white p-2"
            value={scenario}
            onChange={(event) => {
              setScenario(event.target.value as Scenario)
              setChecked(false)
            }}
          >
            {Object.entries(scenarios).map(([key, item]) => (
              <option key={key} value={key}>
                {item.label}
              </option>
            ))}
          </select>
        </label>
      </aside>
      <CheckoutStatus
        state={state}
        summary={checkoutSummary}
        cancelledReturn={scenario === 'cancelled'}
        onCheck={() => setChecked(true)}
        onRetry={() => {
          setScenario('return')
          setChecked(false)
        }}
      />
      {checked && (
        <p role="status" className="text-sm text-slate-600">
          Fixture status checked. Select another scenario to preview a different
          outcome.
        </p>
      )}
    </main>
  )
}
