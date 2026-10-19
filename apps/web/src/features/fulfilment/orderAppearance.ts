import type { TrackingOrder } from './model'

const appearances = {
  attention: {
    label: 'Needs attention',
    border: 'border-red-600',
    text: 'text-red-700',
  },
  waiting: {
    label: 'Waiting',
    border: 'border-amber-500',
    text: 'text-amber-800',
  },
  progress: {
    label: 'In progress',
    border: 'border-blue-500',
    text: 'text-blue-700',
  },
  delivered: {
    label: 'Delivered',
    border: 'border-emerald-600',
    text: 'text-emerald-700',
  },
  refunded: {
    label: 'Refunded',
    border: 'border-slate-400',
    text: 'text-slate-600',
  },
}

export function orderAppearance(order: TrackingOrder) {
  if (order.payment_status === 'refunded') return appearances.refunded
  if (
    order.payment_status === 'refund_required' ||
    order.status === 'exception' ||
    order.status === 'cancelled' ||
    order.quote_check !== 'valid' ||
    (order.delivery &&
      ['unknown', 'failed', 'cancelled'].includes(order.delivery.status))
  )
    return appearances.attention
  if (order.delivery?.status === 'delivered') return appearances.delivered
  if (order.payment_status !== 'succeeded' || order.medicine_status !== 'ready')
    return appearances.waiting
  return appearances.progress
}
