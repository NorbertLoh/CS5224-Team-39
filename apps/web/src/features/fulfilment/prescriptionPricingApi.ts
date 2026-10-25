import { apiFetch } from '../../lib/api'
import { accessToken } from '../clinics/api'

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
export function minorUnits(value: string): number | null {
  const match = /^(\d+)(?:\.(\d{1,2}))?$/.exec(value.trim())
  if (!match) return null
  const amount =
    Number(match[1]) * 100 + Number((match[2] ?? '').padEnd(2, '0'))
  return Number.isSafeInteger(amount) && amount >= 0 ? amount : null
}
export function decimal(minor: number) {
  return `${Math.trunc(minor / 100)}.${String(minor % 100).padStart(2, '0')}`
}

