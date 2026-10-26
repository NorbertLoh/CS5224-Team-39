import type { TrackingOrder } from '@/features/fulfilment/domain/model'
import type { Payment } from '@/features/payments/api'

export type Money = { amount_minor: number; currency: 'SGD' }

export type Order = {
  delivery_snapshot?: Delivery | null
  order_id: string
  tenant_id: string
  patient_id: string
  appointment_id: string
  prescription_id: string
  status: TrackingOrder['status']
  medicine_status: TrackingOrder['medicine_status']
  payment_status: TrackingOrder['payment_status']
  payment_id: string | null
  quote_id: string | null
  delivery_id: string | null
  medication_subtotal: Money
  delivery_fee: Money | null
  total: Money | null
  items: {
    prescription_item_id: string
    medication_id: string
    display_name: string
    quantity: number
    unit_price: Money
    line_total: Money
  }[]
  created_at: string
  updated_at: string
}

export type Quote = {
  contact_confirmed: boolean
  quote_id: string
  order_id: string
  tenant_id: string
  status: 'active' | 'accepted' | 'expired' | 'superseded'
  medication_subtotal: Money
  delivery_fee: Money
  total: Money
  expires_at: string
  created_at: string
}

export type Delivery = {
  delivery_id: string
  order_id: string
  tenant_id: string
  status: NonNullable<TrackingOrder['delivery']>['status']
  created_at: string
  updated_at: string
}

export type Destination = {
  address_line: string
  postal_code: string
  country_code: 'SG'
}

export type RecipientContact = { name: string; phone_number: string }

export type DeliveryDetails = {
  quote_id: string | null
  destination: Destination | null
  recipient: RecipientContact | null
}

export type OrderSnapshot = {
  order: Order
  quote: Quote | null
  payment: Payment | null
  delivery: Delivery | null
}
