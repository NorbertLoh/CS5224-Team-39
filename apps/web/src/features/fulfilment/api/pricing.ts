import { accessToken } from '@/auth/access-token'
import { apiFetch } from '@/lib/api'

type Money = { amount_minor: number; currency: 'SGD' }

type Line = {
  prescription_item_id: string
  display_name: string
  quantity: number
}

export type Prescription = {
  prescription_id: string
  appointment_id: string
  patient_id: string
  created_at: string
  items: Line[]
}

export type Prices = {
  prescription_id: string
  locked: boolean
  items: { prescription_item_id: string; unit_price: Money }[]
}

export async function request(path: string, init: RequestInit = {}) {
  return apiFetch(path, {
    ...init,
    accessToken: await accessToken(),
    signal: init.signal ?? AbortSignal.timeout(15000),
  })
}

export function pricePath(tenantId: string, prescriptionId: string) {
  return `/fulfilment/clinics/${encodeURIComponent(tenantId)}/prescriptions/${encodeURIComponent(prescriptionId)}/prices`
}
