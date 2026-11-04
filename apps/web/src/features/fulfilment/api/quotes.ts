import { request } from './client'
import type {
  DeliveryDetails,
  Destination,
  Quote,
  RecipientContact,
} from './types'

export async function createQuote(
  orderId: string,
  destination: Destination,
  key: string,
  recipient: RecipientContact,
): Promise<Quote> {
  return (
    await request(`/orders/${encodeURIComponent(orderId)}/quotes`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Idempotency-Key': key },
      body: JSON.stringify({ destination, recipient }),
    })
  ).json()
}

export async function readDeliveryDetails(
  orderId: string,
  signal?: AbortSignal,
): Promise<DeliveryDetails> {
  return (
    await request(`/orders/${encodeURIComponent(orderId)}/delivery-details`, {
      signal,
    })
  ).json()
}
