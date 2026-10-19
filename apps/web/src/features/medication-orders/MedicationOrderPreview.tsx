import { useEffect, useReducer, useState } from 'react'
import { DeliveryQuote } from './DeliveryQuote'
import { MedicationPayment, paymentOutcomes } from './MedicationPayment'
import { OrderSummary } from './OrderSummary'
import { initialState, orderReducer, singaporeTime } from './model'
import type { Outcome } from './model'

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

function OrderFlow() {
  const [state, dispatch] = useReducer(orderReducer, undefined, initialState)
  const [outcome, setOutcome] = useState<Outcome>('pending')
  const [unavailable, setUnavailable] = useState(false)
  useEffect(() => {
    let previous = Date.now()
    const timer = window.setInterval(() => {
      const current = Date.now()
      dispatch({ type: 'tick', elapsed: current - previous })
      previous = current
    }, 1000)
    return () => window.clearInterval(timer)
  }, [])
  return (
    <>
      <OrderSummary state={state} />
      {!state.created ? (
        <button
          className="rounded-lg bg-slate-900 px-4 py-2 text-white"
          onClick={() => dispatch({ type: 'create' })}
        >
          Create demo medication order
        </button>
      ) : (
        <>
          <details className="rounded-xl border p-4 text-sm">
            <summary className="cursor-pointer font-medium">
              Preview controls
            </summary>
            <div className="mt-3 space-y-3">
              <p>
                Demo clock: {singaporeTime(state.now)}. It advances while this
                page is open.
              </p>
              <label className="block">
                <input
                  type="checkbox"
                  checked={unavailable}
                  onChange={(event) => setUnavailable(event.target.checked)}
                />{' '}
                Simulate unavailable delivery quote
              </label>
              <label className="block">
                Next payment status check
                <select
                  className="mt-1 block w-full rounded border bg-white p-2"
                  value={outcome}
                  onChange={(event) =>
                    setOutcome(event.target.value as Outcome)
                  }
                >
                  {Object.entries(paymentOutcomes).map(([key, label]) => (
                    <option key={key} value={key}>
                      {label}
                    </option>
                  ))}
                </select>
              </label>
              <button
                className="rounded border px-4 py-2"
                disabled={!state.quote}
                onClick={() => dispatch({ type: 'expire' })}
              >
                Advance to quote deadline
              </button>
              <p>
                Changing a preview control applies only when you request a quote
                or check payment status.
              </p>
            </div>
          </details>
          <DeliveryQuote
            state={state}
            dispatch={dispatch}
            unavailable={unavailable}
          />
          <MedicationPayment
            state={state}
            outcome={outcome}
            dispatch={dispatch}
          />
        </>
      )}
    </>
  )
}
