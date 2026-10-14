import shared from '../../../../../dev/fixtures/telelink.json'

export type Slot = {
  slot_id: string
  tenant_id: string
  doctor_id: string
  starts_at: string
  ends_at: string
  availability: string
}

export const fixtureClinics = shared.clinics.filter(clinic => clinic.status === 'active')
export function fixtureDoctors(tenantId: string) {
  return shared.subjects.filter(subject => shared.memberships.some(member =>
    member.subject_id === subject.subject_id && member.tenant_id === tenantId &&
    member.status === 'active' && member.roles.includes('doctor')))
}

// Preserve the agreed fixture intervals, moving the earliest day to tomorrow.
export function initialSlots(now = Date.now()): Slot[] {
  const earliestDay = Math.min(...shared.slots.map(slot => Date.parse(slot.starts_at.slice(0, 10))))
  const tomorrow = Date.parse(singaporeDate(now)) + 86400000
  const offset = tomorrow - earliestDay
  return shared.slots.map(slot => ({ ...slot,
    starts_at: new Date(Date.parse(slot.starts_at) + offset).toISOString(),
    ends_at: new Date(Date.parse(slot.ends_at) + offset).toISOString(),
  }))
}

export function singaporeDate(now = Date.now()) {
  return new Date(now + 8 * 3600000).toISOString().slice(0, 10)
}

export function slotStart(date: string, time: string) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(date) || !/^\d{2}:\d{2}$/.test(time)) return NaN
  const value = Date.parse(`${date}T${time}:00+08:00`)
  // Reject calendar rollovers as well as malformed input.
  if (!Number.isFinite(value) || new Date(value + 8 * 3600000).toISOString().slice(0, 16) !== `${date}T${time}`) return NaN
  return value
}

export function addSlot(slots: Slot[], tenantId: string, doctorId: string, date: string, time: string, now = Date.now()): Slot[] {
  if (!fixtureDoctors(tenantId).some(doctor => doctor.subject_id === doctorId)) throw new Error('Choose an active fixture doctor and clinic.')
  const start = slotStart(date, time)
  if (!Number.isFinite(start)) throw new Error('Enter a valid date and start time.')
  if (start <= now) throw new Error('Choose a start time in the future.')
  const end = start + 30 * 60000
  if (slots.some(slot => slot.doctor_id === doctorId && Date.parse(slot.starts_at) < end && Date.parse(slot.ends_at) > start)) {
    throw new Error('This doctor already has an overlapping slot, possibly at another clinic.')
  }
  return [...slots, { slot_id: crypto.randomUUID(), tenant_id: tenantId, doctor_id: doctorId,
    starts_at: new Date(start).toISOString(), ends_at: new Date(end).toISOString(), availability: 'available' }]
}

export function removeSlot(slots: Slot[], slotId: string, tenantId: string, doctorId: string, now = Date.now()): Slot[] {
  const slot = slots.find(item => item.slot_id === slotId && item.tenant_id === tenantId && item.doctor_id === doctorId)
  if (!slot) throw new Error('This slot is no longer available in the selected schedule.')
  if (slot.availability !== 'available') throw new Error('Unavailable slots cannot be removed.')
  if (Date.parse(slot.starts_at) <= now) throw new Error('Past slots cannot be removed.')
  return slots.filter(item => item.slot_id !== slotId)
}

export function formatSlotTime(instant: string) {
  return new Intl.DateTimeFormat('en-SG', { timeZone: 'Asia/Singapore', hour: '2-digit', minute: '2-digit', hour12: false }).format(new Date(instant))
}
