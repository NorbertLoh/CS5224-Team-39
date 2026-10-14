import assert from 'node:assert/strict'
import { test } from 'node:test'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { AvailabilityEditor } from '../src/features/availability/AvailabilityEditor'
import { addSlot, fixtureClinics, fixtureDoctors, initialSlots, removeSlot, singaporeDate, slotStart } from '../src/features/availability/fixtures'

const now = Date.parse('2026-10-14T03:00:00Z')
const clinicA = fixtureClinics[0].tenant_id
const clinicB = fixtureClinics[1].tenant_id
const doctor = fixtureDoctors(clinicA).find(item => fixtureDoctors(clinicB).some(other => other.subject_id === item.subject_id))!.subject_id

test('SGT date and slot input work independently of browser timezone and reject rollovers', () => {
  assert.equal(singaporeDate(Date.parse('2026-10-14T18:00:00Z')), '2026-10-15')
  assert.equal(slotStart('2026-10-15', '09:00'), Date.parse('2026-10-15T01:00:00Z'))
  for (const [date, time] of [['2026-02-30', '09:00'], ['', '09:00'], ['2026-10-15', '24:00'], ['2026-10-15', '09:60']]) {
    assert.ok(Number.isNaN(slotStart(date, time)))
  }
})

test('fixture dates remain future, preserve intervals and exclude former doctors', () => {
  const slots = initialSlots(now)
  assert.ok(slots.every(slot => Date.parse(slot.starts_at) > now))
  assert.ok(slots.every(slot => Date.parse(slot.ends_at) - Date.parse(slot.starts_at) === 1800000))
  assert.equal(Math.min(...slots.map(slot => Date.parse(slot.starts_at.slice(0, 10)))), Date.parse('2026-10-15'))
  assert.ok(fixtureDoctors(clinicA).every(item => item.display_name !== 'Demo Former Doctor'))
})

test('half-open slots allow adjacent times but reject duplicates and cross-clinic overlaps', () => {
  const slots = addSlot([], clinicA, doctor, '2026-10-15', '09:00', now)
  for (const time of ['08:45', '09:00', '09:15']) {
    assert.throws(() => addSlot(slots, clinicB, doctor, '2026-10-15', time, now), /overlapping/)
  }
  assert.equal(addSlot(slots, clinicB, doctor, '2026-10-15', '09:30', now).length, 2)
  assert.equal(addSlot(slots, clinicB, doctor, '2026-10-15', '08:30', now).length, 2)
  assert.equal(slots.length, 1)
  assert.equal(slots[0].starts_at, '2026-10-15T01:00:00.000Z')
})

test('creation rejects past, invalid and inactive-context input', () => {
  assert.throws(() => addSlot([], clinicA, doctor, '2026-10-14', '11:00', now), /future/)
  assert.throws(() => addSlot([], clinicA, doctor, '2026-02-30', '09:00', now), /valid date/)
  assert.throws(() => addSlot([], clinicA, 'unrelated-doctor', '2026-10-15', '09:00', now), /active fixture doctor/)
})

test('removal protects unavailable, past and other-context slots and leaves input intact', () => {
  const slots = addSlot([], clinicA, doctor, '2026-10-15', '09:00', now)
  const id = slots[0].slot_id
  assert.throws(() => removeSlot(slots, id, clinicB, doctor, now), /selected schedule/)
  assert.throws(() => removeSlot([{ ...slots[0], availability: 'unavailable' }], id, clinicA, doctor, now), /Unavailable/)
  assert.throws(() => removeSlot(slots, id, clinicA, doctor, Date.parse(slots[0].starts_at)), /Past/)
  assert.deepEqual(removeSlot(slots, id, clinicA, doctor, now), [])
  assert.equal(slots.length, 1)
})

test('editor identifies fixture-only data and timezone and uses accessible labelled inputs', () => {
  const markup = renderToStaticMarkup(createElement(AvailabilityEditor))
  assert.match(markup, /Fixture preview/)
  assert.match(markup, /do not change real availability/)
  assert.match(markup, /Singapore time/)
  assert.match(markup, /type="date"/)
  assert.match(markup, /type="time"/)
  assert.match(markup, /role="status"/)
})
