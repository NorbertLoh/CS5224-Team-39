/** Real S07 adapters through Vite; launched by check_scheduling_frontend.py. */
import assert from 'node:assert/strict'
import {
  createHold,
  createSlot,
  removeSlot,
  listSlots,
  listAppointments,
  appointmentDetail,
  cancelAppointment,
} from '../apps/web/src/features/scheduling/api'
import { currentIdentity } from '../apps/web/src/auth/identity'
import { ApiError } from '../apps/web/src/lib/api'

const run = JSON.parse(process.env.S07_CONTEXT ?? '{}')
assert.ok(
  run.clinics?.length === 2 && run.tokens,
  'Run the Python orchestrator.',
)
const nativeFetch = globalThis.fetch
globalThis.fetch = (input, init) => {
  assert.equal(typeof input, 'string')
  assert.ok(String(input).startsWith('/api/v1/'))
  return nativeFetch(`http://127.0.0.1:5173${input}`, init)
}
const values = new Map<string, string>()
Object.defineProperty(globalThis, 'localStorage', {
  value: {
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => {
      values.set(key, value)
    },
    removeItem: (key: string) => {
      values.delete(key)
    },
  },
})
function signIn(role: string) {
  values.set(
    'telelink.session',
    JSON.stringify({
      accessToken: run.tokens[role].access_token,
      refreshToken: run.tokens[role].refresh_token,
      expiresAt: Date.now() + 1800000,
    }),
  )
}
const slots: string[] = []
const appointments: string[] = []
const start = new Date(Date.now() + 3 * 86400000)
start.setUTCMinutes(0, 0, 0)
const from = start.toISOString()
const to = new Date(start.getTime() + 86400000).toISOString()
try {
  signIn('doctor')
  const doctor = await currentIdentity()
  for (let index = 0; index < 2; index++) {
    const slot = await createSlot(
      run.clinics[index],
      new Date(start.getTime() + index * 1800000).toISOString(),
    )
    assert.equal(slot.doctor_id, doctor.subject_id)
    slots.push(slot.slot_id)
    assert.ok(
      (await listSlots(run.clinics[index], from, to, doctor.subject_id)).some(
        (item) =>
          item.slot_id === slot.slot_id && item.availability === 'available',
      ),
    )
  }
  signIn('patient')
  for (let index = 0; index < 2; index++) {
    const hold = await createHold(run.clinics[index], slots[index])
    appointments.push(hold.appointment_id)
    assert.equal(hold.status, 'held')
    assert.equal(hold.consultation_price.amount_minor, 3210)
    assert.ok(Date.parse(hold.hold_expires_at!) > Date.now())
    assert.equal(
      (await appointmentDetail(hold.appointment_id)).appointment_id,
      hold.appointment_id,
    )
    assert.equal(
      (await listSlots(run.clinics[index], from, to))[0].availability,
      'unavailable',
    )
    await assert.rejects(
      createHold(run.clinics[index], slots[index]),
      (error) => error instanceof ApiError && error.status === 409,
    )
  }
  const patientList = await listAppointments()
  assert.ok(
    appointments.every((id) =>
      patientList.items.some((item) => item.appointment_id === id),
    ),
  )
  signIn('doctor')
  assert.ok(
    (await listAppointments(run.clinics[0])).items.some(
      (item) => item.appointment_id === appointments[0],
    ),
  )
  await assert.rejects(
    cancelAppointment(appointments[0], 'Doctor cannot cancel'),
    (error) => error instanceof ApiError && error.status === 404,
  )
  await assert.rejects(
    removeSlot(slots[0]),
    (error) => error instanceof ApiError && error.status === 409,
  )
  signIn('clinic')
  const clinicList = await listAppointments(run.clinics[0])
  assert.ok(
    clinicList.items.some((item) => item.appointment_id === appointments[0]),
  )
  assert.ok(clinicList.items.every((item) => item.tenant_id === run.clinics[0]))
  assert.equal(
    (await cancelAppointment(appointments[0], 'S07 synthetic cleanup')).status,
    'cancelled',
  )
  assert.equal(
    (await cancelAppointment(appointments[0], 'Idempotent retry')).status,
    'cancelled',
  )
  assert.equal(
    (await listSlots(run.clinics[0], from, to))[0].availability,
    'available',
  )
  console.log(
    'S07 real frontend adapters passed: availability, slots, trusted holds, conflicts, role reads, detail, cancellation and release through Vite.',
  )
} finally {
  signIn('patient')
  for (const id of appointments)
    await cancelAppointment(id, 'S07 synthetic cleanup')
  signIn('doctor')
  for (const id of slots) await removeSlot(id)
}
