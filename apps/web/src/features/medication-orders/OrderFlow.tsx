import { useEffect, useReducer, useState } from 'react'
import { DeliveryQuote } from './DeliveryQuote'
import { MedicationPayment } from './MedicationPayment'
import { OrderSummary } from './OrderSummary'
import { PreviewControls } from './PreviewControls'
import { initialState, orderReducer } from './model'
import type { Outcome } from './model'

export function OrderFlow() {
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
          <PreviewControls
            now={state.now}
            hasQuote={state.quote !== null}
            unavailable={unavailable}
            outcome={outcome}
            onUnavailableChange={setUnavailable}
            onOutcomeChange={setOutcome}
            onExpire={() => dispatch({ type: 'expire' })}
          />
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
