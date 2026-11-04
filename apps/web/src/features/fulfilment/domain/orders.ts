import type { OrderContext } from '@/features/fulfilment/domain/model'
import type { Order } from '../api/types'

export function ownsOrder(order: Order, context: OrderContext) {
  return context.role === 'patient'
    ? order.patient_id === context.patientId
    : order.tenant_id === context.tenantId
}
