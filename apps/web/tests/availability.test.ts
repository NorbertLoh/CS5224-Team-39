import assert from 'node:assert/strict'
import { test } from 'node:test'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { AvailabilityEditor } from '../src/features/availability/AvailabilityEditor'
import { applySelection, cellsInSelection, cellsInSelections, deselectCell, shiftDate, updateSelections, weekStart } from '../src/features/availability/timetable'
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
  assert.match(markup, /Weekly availability timetable/)
  assert.match(markup, /Add availability/)
  assert.match(markup, /Shift \+ arrows/)
  assert.match(markup, /role="status"/)
})

test('reverse rectangular selection spans half-hour cells across a week boundary', () => {
  assert.equal(weekStart('2026-11-01'), '2026-10-26')
  const dates = Array.from({ length: 7 }, (_, index) => shiftDate('2026-10-26', index))
  const cells = cellsInSelection({ from: { day: 6, row: 19 }, to: { day: 5, row: 18 } }, dates)
  assert.deepEqual(cells.map(cell => [cell.date, cell.time]), [['2026-10-31', '09:00'], ['2026-10-31', '09:30'], ['2026-11-01', '09:00'], ['2026-11-01', '09:30']])
})

test('range operations are atomic when any selected slot conflicts or is protected', () => {
  const dates = Array.from({ length: 7 }, (_, index) => shiftDate('2026-10-15', index))
  const range = { from: { day: 0, row: 18 }, to: { day: 0, row: 20 } }
  const blocked = addSlot([], clinicA, doctor, dates[0], '10:00', now)
  const snapshot = JSON.stringify(blocked)
  assert.throws(() => applySelection(blocked, clinicA, doctor, [range], dates, 'add', now), /overlapping/)
  assert.equal(JSON.stringify(blocked), snapshot)
  const added = applySelection([], clinicA, doctor, [range], dates, 'add', now)
  assert.equal(added.length, 3)
  assert.deepEqual(applySelection(added, clinicA, doctor, [range], dates, 'remove', now), [])
  const reserved = added.map((slot, index) => index === 2 ? { ...slot, availability: 'unavailable' } : slot)
  assert.throws(() => applySelection(reserved, clinicA, doctor, [range], dates, 'remove', now), /Unavailable/)
  assert.equal(reserved.length, 3)
  assert.throws(() => applySelection(blocked, clinicB, doctor, [range], dates, 'remove', now), /another clinic/)
})

test('separate ranges retain gaps and overlapping drags do not duplicate slots', () => {
  const dates = Array.from({ length: 7 }, (_, index) => shiftDate('2026-10-15', index))
  const first = { from: { day: 0, row: 18 }, to: { day: 0, row: 19 } }
  const second = { from: { day: 0, row: 26 }, to: { day: 0, row: 27 } }
  let ranges = updateSelections([], first)
  ranges = updateSelections(ranges, { from: second.from, to: second.from })
  ranges = updateSelections(ranges, second, true)
  assert.deepEqual(ranges, [first, second])
  assert.deepEqual(cellsInSelections(ranges, dates).map(cell => cell.time), ['09:00', '09:30', '13:00', '13:30'])
  const repeated = updateSelections(ranges, first)
  assert.equal(cellsInSelections(repeated, dates).length, 4)
  const added = applySelection([], clinicA, doctor, repeated, dates, 'add', now)
  assert.equal(added.length, 4)
  assert.deepEqual(applySelection(added, clinicA, doctor, repeated, dates, 'remove', now), [])
  assert.deepEqual(updateSelections(ranges, null), [])
})

test('deselecting a cell removes it from every overlapping range and preserves all other cells', () => {
  const dates = Array.from({ length: 7 }, (_, index) => shiftDate('2026-10-15', index))
  const ranges = [
    { from: { day: 2, row: 20 }, to: { day: 0, row: 18 } },
    { from: { day: 1, row: 19 }, to: { day: 1, row: 19 } },
    { from: { day: 5, row: 26 }, to: { day: 5, row: 27 } },
  ]
  const before = cellsInSelections(ranges, dates)
  for (let day = 0; day < 3; day++) for (let row = 18; row <= 20; row++) {
    const remaining = cellsInSelections(deselectCell(ranges, { day, row }), dates)
    assert.deepEqual(remaining, before.filter(cell => cell.date !== dates[day] || cell.time !== `${String(Math.floor(row / 2)).padStart(2, '0')}:${row % 2 ? '30' : '00'}`))
  }
  const single = [{ from: { day: 1, row: 19 }, to: { day: 1, row: 19 } }]
  assert.deepEqual(deselectCell(single, { day: 1, row: 19 }), [])
  assert.deepEqual(deselectCell(single, { day: 4, row: 10 }), single)
  assert.equal(cellsInSelections(ranges, dates).length, 11)
})
