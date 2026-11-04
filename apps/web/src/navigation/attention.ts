import type { DoctorApplication } from '@/features/doctor-onboarding/api'
import type { Order } from '@/features/fulfilment/api'
import type { Appointment } from '@/features/scheduling/api'

export type NavigationAttention = {
  tone: 'danger' | 'waiting'
  label: string
  count?: number
  description: string
}

export function verificationAttention(
  application: Pick<DoctorApplication, 'status'> | null,
): NavigationAttention | undefined {
  if (application?.status === 'approved') return undefined
  if (application?.status === 'pending')
    return {
      tone: 'waiting',
      label: 'In review',
      description: 'Your doctor application is awaiting platform review.',
    }
  return {
    tone: 'danger',
    label: 'Action needed',
    description: application
      ? 'Update and resubmit your doctor verification.'
      : 'Submit your professional details and licence for verification.',
  }
}

export function pendingAttention(
  count: number | undefined,
  description: string,
): NavigationAttention | undefined {
  return count && count > 0
    ? { tone: 'danger', label: 'Pending', count, description }
    : undefined
}

export function appointmentPaymentAttention(
  appointments: Pick<
    Appointment,
    | 'patient_id'
    | 'status'
    | 'payment_resolution'
    | 'hold_expires_at'
    | 'ends_at'
  >[],
  subject: string,
  now = Date.now(),
): NavigationAttention | undefined {
  const count = appointments.filter(
    (item) =>
      item.patient_id === subject &&
      ['held', 'pending_payment'].includes(item.status) &&
      ['none', 'awaiting_payment'].includes(item.payment_resolution) &&
      item.hold_expires_at &&
      Date.parse(item.hold_expires_at) > now &&
      Date.parse(item.ends_at) > now,
  ).length
  return count
    ? {
        tone: 'danger',
        label: 'Payment due',
        count,
        description: `${count} appointment booking${count === 1 ? '' : 's'} awaiting payment. Open Appointments to review.`,
      }
    : undefined
}

export function orderAttention(
  orders: Pick<Order, 'patient_id' | 'payment_status' | 'status'>[],
  subject: string,
): NavigationAttention | undefined {
  const own = orders.filter(
    (order) =>
      order.patient_id === subject &&
      order.payment_status !== 'refunded' &&
      order.status !== 'delivered',
  )
  const action = own.filter(
    (order) =>
      order.status === 'exception' ||
      order.payment_status === 'refund_required' ||
      (order.status === 'awaiting_payment' &&
        order.payment_status === 'unpaid'),
  ).length
  const progress = own.filter(
    (order) =>
      (order.payment_status !== 'refund_required' &&
        ['paid', 'submitting', 'dispatched'].includes(order.status)) ||
      (order.status === 'awaiting_payment' &&
        order.payment_status === 'pending'),
  ).length
  if (action)
    return {
      tone: 'danger',
      label: 'Needs attention',
      count: action,
      description: `${action} order${action === 1 ? '' : 's'} need payment or review; ${progress} in progress. Open Orders & delivery.`,
    }
  return progress
    ? {
        tone: 'waiting',
        label: 'In progress',
        count: progress,
        description: `${progress} order${progress === 1 ? '' : 's'} awaiting payment confirmation, preparation or delivery.`,
      }
    : undefined
}
