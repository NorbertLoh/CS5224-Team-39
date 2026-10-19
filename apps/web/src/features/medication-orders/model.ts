import contract from '../../../../../contracts/examples/prescription-order-quote.json'

export const order = contract.order_after_payment
export const prescription = contract.prescription
export const fixtureNow = Date.parse('2026-10-12T03:00:00Z')
export type Address = {
  address_line: string
  postal_code: string
  country_code: 'SG'
}
export type Quote = {
  quote_id: string
  destination: Address
  expiresAt: number
  medicationSubtotal: number
  deliveryFee: number
  total: number
}
export type PaymentState =
  | 'none'
  | 'pending'
  | 'unknown'
  | 'failed'
  | 'confirming'
  | 'paid'
  | 'refund_required'
export type Outcome = Exclude<PaymentState, 'none'> | 'cancelled'
export type OrderState = {
  created: boolean
  address: Address
  quote: Quote | null
  payment: PaymentState
  cancelledReturn: boolean
  now: number
  quoteVersion: number
  error: string | null
}
export type Action =
  | { type: 'create' }
  | { type: 'address'; field: 'address_line' | 'postal_code'; value: string }
  | { type: 'quote'; unavailable?: boolean }
  | { type: 'checkout' }
  | { type: 'check'; outcome: Outcome }
  | { type: 'tick'; elapsed: number }
  | { type: 'expire' }

export function initialState(): OrderState {
  return {
    created: false,
    address: {
      address_line: '10 Demo Street #01-01',
      postal_code: '018956',
      country_code: 'SG',
    },
    quote: null,
    payment: 'none',
    cancelledReturn: false,
    now: fixtureNow,
    quoteVersion: 0,
    error: null,
  }
}

export function addressError(address: Address) {
  if (!address.address_line.trim() || address.address_line.trim().length > 240)
    return 'Enter a delivery address of 1 to 240 characters.'
  if (!/^[0-9]{6}$/.test(address.postal_code.trim()))
    return 'Enter a six-digit Singapore postal code.'
  return null
}

export function canEdit(state: OrderState) {
  return state.payment === 'none' || state.payment === 'failed'
}

export function canCheckout(state: OrderState) {
  return (
    state.created &&
    canEdit(state) &&
    state.quote !== null &&
    state.now < state.quote.expiresAt
  )
}

// This reducer simulates the C04 boundary; it never authorizes a real checkout.
export function orderReducer(state: OrderState, action: Action): OrderState {
  switch (action.type) {
    case 'create':
      return { ...state, created: true }
    case 'tick':
      return { ...state, now: state.now + Math.max(0, action.elapsed) }
    case 'expire':
      return state.quote
        ? { ...state, now: Math.max(state.now, state.quote.expiresAt) }
        : state
    case 'address':
      if (!canEdit(state)) return state
      return {
        ...state,
        address: { ...state.address, [action.field]: action.value },
        quote: null,
        payment: 'none',
        error: null,
      }
    case 'quote': {
      if (!state.created || !canEdit(state)) return state
      const error = addressError(state.address)
      if (error || action.unavailable)
        return {
          ...state,
          quote: null,
          error:
            error ??
            'Delivery quote unavailable. Try requesting a quote again.',
        }
      return {
        ...state,
        quoteVersion: state.quoteVersion + 1,
        payment: 'none',
        error: null,
        quote: {
          quote_id: `${contract.accepted_quote.quote_id}-preview-${state.quoteVersion + 1}`,
          destination: {
            ...state.address,
            address_line: state.address.address_line.trim(),
            postal_code: state.address.postal_code.trim(),
          },
          expiresAt: state.now + 10 * 60_000,
          medicationSubtotal:
            contract.accepted_quote.medication_subtotal.amount_minor,
          deliveryFee: contract.accepted_quote.delivery_fee.amount_minor,
          total: contract.accepted_quote.total.amount_minor,
        },
      }
    }
    case 'checkout':
      return canCheckout(state)
        ? { ...state, payment: 'pending', cancelledReturn: false, error: null }
        : state
    case 'check':
      if (!['pending', 'unknown', 'confirming'].includes(state.payment))
        return state
      // A failed status read or an older outcome cannot undo known payment success.
      if (
        state.payment === 'confirming' &&
        !['paid', 'refund_required'].includes(action.outcome)
      )
        return state
      if (action.outcome === 'cancelled')
        return { ...state, payment: 'pending', cancelledReturn: true }
      return { ...state, payment: action.outcome, cancelledReturn: false }
  }
}

export function money(amountMinor: number) {
  return new Intl.NumberFormat('en-SG', {
    style: 'currency',
    currency: 'SGD',
  }).format(amountMinor / 100)
}

export function singaporeTime(instant: number) {
  return (
    new Intl.DateTimeFormat('en-SG', {
      timeZone: 'Asia/Singapore',
      dateStyle: 'medium',
      timeStyle: 'medium',
    }).format(instant) + ' SGT'
  )
}
