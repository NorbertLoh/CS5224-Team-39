import type { TrackingOrder } from '@/features/fulfilment/domain/model'

const appearances = {
  attention: {
    label: 'Needs attention',
    border: 'border-red-600',
    text: 'text-red-700',
    badge: 'bg-red-50 text-red-700 ring-red-200',
  },
  waiting: {
    label: 'Waiting',
    border: 'border-amber-500',
    text: 'text-amber-800',
    badge: 'bg-amber-50 text-amber-800 ring-amber-200',
  },
  progress: {
    label: 'In progress',
    border: 'border-blue-500',
    text: 'text-blue-700',
    badge: 'bg-blue-50 text-blue-700 ring-blue-200',
  },
  delivered: {
    label: 'Delivered',
    border: 'border-emerald-600',
    text: 'text-emerald-700',
    badge: 'bg-emerald-50 text-emerald-800 ring-emerald-200',
  },
  refunded: {
    label: 'Refunded',
    border: 'border-slate-400',
    text: 'text-slate-600',
    badge: 'bg-slate-100 text-slate-700 ring-slate-200',
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
  if (order.status === 'delivered' || order.delivery?.status === 'delivered')
    return appearances.delivered
  if (order.payment_status !== 'succeeded' || order.medicine_status !== 'ready')
    return appearances.waiting
  return appearances.progress
}
