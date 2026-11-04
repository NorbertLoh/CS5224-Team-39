import type { CursorPage } from '@/lib/api-types'
import { request } from './client'
import type { Delivery, Order } from './types'

export async function listOrders(
  tenantId?: string,
  cursor?: string | null,
  signal?: AbortSignal,
  sort: 'oldest' | 'newest' = 'newest',
): Promise<CursorPage<Order>> {
  const params = new URLSearchParams({ limit: '25' })
  params.set('sort', sort)
  if (tenantId) params.set('tenant_id', tenantId)
  if (cursor) params.set('cursor', cursor)
  const page: CursorPage<Order> = await (
    await request(`/orders?${params}`, { signal })
  ).json()
  const items = await Promise.all(
    page.items.map(async (order) => {
      if (!order.delivery_id) return order
      const delivery: Delivery = await (
        await request(`/deliveries/${encodeURIComponent(order.delivery_id)}`, {
          signal,
        })
      ).json()
      if (
        delivery.delivery_id !== order.delivery_id ||
        delivery.order_id !== order.order_id ||
        delivery.tenant_id !== order.tenant_id
      )
        throw new Error('Delivery unavailable.')
      return { ...order, delivery_snapshot: delivery }
    }),
  )
  return { items, next_cursor: page.next_cursor }
}

export async function readOrder(
  id: string,
  signal?: AbortSignal,
): Promise<Order> {
  return (await request(`/orders/${encodeURIComponent(id)}`, { signal })).json()
}

export async function createOrder(
  prescriptionId: string,
  key: string,
): Promise<Order> {
  return (
    await request('/orders', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Idempotency-Key': key },
      body: JSON.stringify({ prescription_id: prescriptionId }),
    })
  ).json()
}

export async function readyOrder(id: string): Promise<Order> {
  return (
    await request(`/orders/${encodeURIComponent(id)}/ready`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: '{}',
    })
  ).json()
}
