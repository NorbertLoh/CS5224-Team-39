export type CheckoutSnapshot = {
  payment:
    | 'pending'
    | 'failed'
    | 'succeeded'
    | 'refund_pending'
    | 'refunded'
    | 'refund_failed'
  appointment: 'pending_payment' | 'confirmed' | 'expired' | 'cancelled'
  resolution: 'awaiting_payment' | 'confirmed' | 'refund_required' | 'refunded'
  holdExpiresAt: string | null
}

export type CheckoutState =
  | 'pending'
  | 'failed'
  | 'success'
  | 'expired'
  | 'cancelled'
  | 'confirming'
  | 'refund_required'
  | 'refund_pending'
  | 'refunded'

// B07 must supply authenticated billing/scheduling reads here, never redirect data.
export function checkoutState(
  snapshot: CheckoutSnapshot,
  now: number,
): CheckoutState {
  if (snapshot.payment === 'refunded' || snapshot.resolution === 'refunded')
    return 'refunded'
  if (snapshot.payment === 'refund_pending') return 'refund_pending'
  if (
    snapshot.resolution === 'refund_required' ||
    snapshot.payment === 'refund_failed'
  )
    return 'refund_required'
  if (snapshot.payment === 'succeeded') {
    return snapshot.appointment === 'confirmed' &&
      snapshot.resolution === 'confirmed'
      ? 'success'
      : 'confirming'
  }
  if (snapshot.appointment === 'cancelled') return 'cancelled'
  const deadline = snapshot.holdExpiresAt
    ? Date.parse(snapshot.holdExpiresAt)
    : NaN
  if (
    snapshot.appointment === 'expired' ||
    !Number.isFinite(deadline) ||
    now >= deadline
  )
    return 'expired'
  return snapshot.payment === 'failed' ? 'failed' : 'pending'
}
