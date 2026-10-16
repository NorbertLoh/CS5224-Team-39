import shared from '../../../../../dev/fixtures/telelink.json'
import type { Clinic, Doctor } from '../clinics/api'

export type BookingSlot = {
  slot_id: string
  tenant_id: string
  doctor_id: string
  doctor_name: string
  starts_at: string
  ends_at: string
  availability: string
  consultation_price: Clinic['consultation_price']
}
export type BookingHold = {
  appointment_id: string
  slot: BookingSlot
  status: 'pending_payment'
  hold_expires_at: string
}

export function singaporeDate(now: number) {
  return new Date(now + 8 * 3600000).toISOString().slice(0, 10)
}
export function bookingDates(now = Date.now()) {
  const today = Date.parse(singaporeDate(now))
  return [1, 2, 3].map((day) =>
    new Date(today + day * 86400000).toISOString().slice(0, 10),
  )
}
export function demoSlots(
  clinic: Clinic,
  doctors: Doctor[],
  now = Date.now(),
): BookingSlot[] {
  if (clinic.status !== 'active') return []
  return bookingDates(now)
    .flatMap((date, day) =>
      doctors.flatMap((doctor) =>
        Array.from({ length: 16 }, (_, index) => {
          const start = Date.parse(`${date}T09:00:00+08:00`) + index * 1800000
          const template = shared.slots[(index + day) % shared.slots.length]
          return {
            slot_id: `${doctor.doctor_id}:${date}:${index}`,
            tenant_id: clinic.tenant_id,
            doctor_id: doctor.doctor_id,
            doctor_name: doctor.display_name,
            starts_at: new Date(start).toISOString(),
            ends_at: new Date(start + 1800000).toISOString(),
            availability: template.availability,
            consultation_price: { ...clinic.consultation_price },
          }
        }),
      ),
    )
    .sort(
      (a, b) =>
        a.starts_at.localeCompare(b.starts_at) ||
        a.doctor_name.localeCompare(b.doctor_name),
    )
}
export function createDemoHold(
  slots: BookingSlot[],
  slotId: string,
  tenantId: string,
  now = Date.now(),
): BookingHold {
  const slot = slots.find(
    (item) => item.slot_id === slotId && item.tenant_id === tenantId,
  )
  if (
    !slot ||
    slot.availability !== 'available' ||
    Date.parse(slot.starts_at) <= now
  )
    throw new Error('That slot is no longer available. Choose another time.')
  return {
    appointment_id: crypto.randomUUID(),
    slot: { ...slot, consultation_price: { ...slot.consultation_price } },
    status: 'pending_payment',
    hold_expires_at: new Date(
      Math.min(now + 10 * 60000, Date.parse(slot.starts_at)),
    ).toISOString(),
  }
}
export function holdSeconds(hold: BookingHold, now = Date.now()) {
  return Math.max(0, Math.ceil((Date.parse(hold.hold_expires_at) - now) / 1000))
}
export function formatBookingDate(date: string) {
  return new Intl.DateTimeFormat('en-SG', {
    timeZone: 'Asia/Singapore',
    weekday: 'short',
    day: 'numeric',
    month: 'short',
  }).format(new Date(`${date}T00:00:00+08:00`))
}
export function formatBookingTime(instant: string) {
  return new Intl.DateTimeFormat('en-SG', {
    timeZone: 'Asia/Singapore',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(new Date(instant))
}
