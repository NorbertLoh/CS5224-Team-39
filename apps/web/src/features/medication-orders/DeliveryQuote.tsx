import type { Dispatch } from 'react'
import { canCheckout, canEdit, singaporeTime } from './model'
import type { Action, OrderState } from './model'

export function DeliveryQuote({
  state,
  dispatch,
  unavailable,
}: {
  state: OrderState
  dispatch: Dispatch<Action>
  unavailable: boolean
}) {
  const editable = canEdit(state)
  const expired = state.quote !== null && state.now >= state.quote.expiresAt
  return (
    <section
      className="space-y-4 rounded-xl border p-5"
      aria-labelledby="delivery-heading"
    >
      <h2 id="delivery-heading" className="text-xl font-semibold">
        Delivery quote
      </h2>
      <form
        onSubmit={(event) => {
          event.preventDefault()
          dispatch({ type: 'quote', unavailable })
        }}
      >
        <fieldset
          disabled={!editable}
          className="space-y-4 disabled:opacity-70"
        >
          <legend className="mb-3 text-sm text-slate-600">
            Singapore delivery · use a synthetic address
          </legend>
          <label className="block text-sm font-medium">
            Delivery address
            <input
              required
              maxLength={240}
              autoComplete="off"
              className="mt-1 block w-full rounded-lg border p-2"
              value={state.address.address_line}
              onChange={(event) =>
                dispatch({
                  type: 'address',
                  field: 'address_line',
                  value: event.target.value,
                })
              }
            />
          </label>
          <label className="block text-sm font-medium">
            Postal code
            <input
              required
              pattern="[0-9]{6}"
              maxLength={6}
              inputMode="numeric"
              autoComplete="off"
              className="mt-1 block w-full rounded-lg border p-2"
              value={state.address.postal_code}
              onChange={(event) =>
                dispatch({
                  type: 'address',
                  field: 'postal_code',
                  value: event.target.value,
                })
              }
            />
          </label>
          <p className="text-sm">Country: Singapore (SG)</p>
          <button className="rounded-lg border px-4 py-2" type="submit">
            {state.quote ? 'Refresh demo quote' : 'Request demo quote'}
          </button>
        </fieldset>
      </form>
      {state.error && (
        <p role="alert" className="text-sm text-red-700">
          {state.error}
        </p>
      )}
      {state.quote && (
        <div className="space-y-2 rounded-lg bg-slate-50 p-4 text-sm">
          <p className="font-medium">
            {editable
              ? expired
                ? 'Quote expired'
                : 'Quote active'
              : 'Quote reserved for this payment'}
          </p>
          <p>
            Destination: {state.quote.destination.address_line}, Singapore{' '}
            {state.quote.destination.postal_code}
          </p>
          <p>Quote deadline: {singaporeTime(state.quote.expiresAt)}</p>
          {editable && expired && (
            <p role="status">Request a fresh quote before starting payment.</p>
          )}
          {editable && !expired && (
            <p>
              Changing the address removes this quote. A new quote may change
              the total.
            </p>
          )}
        </div>
      )}
      {editable && (
        <button
          className="rounded-lg bg-slate-900 px-4 py-2 text-white disabled:opacity-50"
          disabled={!canCheckout(state)}
          onClick={() => dispatch({ type: 'checkout' })}
        >
          {state.payment === 'failed'
            ? 'Retry demo payment'
            : 'Preview payment'}
        </button>
      )}
    </section>
  )
}
