import assert from 'node:assert/strict'
import { test } from 'node:test'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import shared from '../../../dev/fixtures/telelink.json'
import type { Clinic } from '../src/features/clinics/api'
import {
  bookingDates,
  createDemoHold,
  demoSlots,
  holdSeconds,
  singaporeDate,
} from '../src/features/booking/fixtures'
import { SlotPicker } from '../src/features/booking/SlotPicker'
import { CheckoutReview } from '../src/features/booking/CheckoutReview'
import { ConsultationCard } from '../src/features/storefront/ConsultationCard'
import { canAccess, parseRoute } from '../src/navigation/access'

const clinic = shared.clinics[0] as Clinic
const doctors = [{ doctor_id: 'local-doctor', display_name: 'Local doctor' }]
const now = Date.parse('2026-10-14T18:00:00Z')

test('clinic Book link enters a patient-protected booking route; inactive clinic cannot book', () => {
  const markup = renderToStaticMarkup(
    createElement(ConsultationCard, {
      price: clinic.consultation_price,
      slug: clinic.slug,
      active: true,
    }),
  )
  assert.match(markup, /Book a consultation/)
  assert.match(markup, /href="\/patient\/clinics\/demo-clinic-a\/book"/)
  const route = parseRoute('/patient/clinics/demo-clinic-a/book')
  assert.deepEqual(route, {
    kind: 'booking',
    role: 'patient',
    slug: 'demo-clinic-a',
  })
  assert.equal(
    canAccess(
      { subject_id: 'patient', global_roles: ['patient'], memberships: [] },
      route,
    ),
    true,
  )
  assert.equal(
    canAccess(
      { subject_id: 'doctor', global_roles: [], memberships: [] },
      route,
    ),
    false,
  )
  const inactive = renderToStaticMarkup(
    createElement(ConsultationCard, {
      price: clinic.consultation_price,
      slug: clinic.slug,
      active: false,
    }),
  )
  assert.match(inactive, /Booking unavailable/)
  assert.doesNotMatch(inactive, /href=/)
})

test('preview generates three future Singapore days with fixed intervals and selected clinic doctors', () => {
  assert.equal(singaporeDate(now), '2026-10-15')
  assert.deepEqual(bookingDates(now), [
    '2026-10-16',
    '2026-10-17',
    '2026-10-18',
  ])
  const slots = demoSlots(clinic, doctors, now)
  assert.equal(slots.length, 48)
  assert.ok(
    slots.every(
      (slot) =>
        slot.tenant_id === clinic.tenant_id &&
        slot.doctor_id === doctors[0].doctor_id &&
        Date.parse(slot.starts_at) > now &&
        Date.parse(slot.ends_at) - Date.parse(slot.starts_at) === 1800000,
    ),
  )
  assert.ok(slots.some((slot) => slot.availability === 'available'))
  assert.ok(slots.some((slot) => slot.availability === 'unavailable'))
  assert.deepEqual(
    demoSlots({ ...clinic, status: 'suspended' }, doctors, now),
    [],
  )
  assert.deepEqual(demoSlots(clinic, [], now), [])
})

test('checkout requires an available clinic slot, snapshots fee and honors exact hold expiry', () => {
  const slots = demoSlots(clinic, doctors, now)
  const slot = slots.find((item) => item.availability === 'available')!
  const unavailable = slots.find((item) => item.availability !== 'available')!
  assert.throws(
    () => createDemoHold(slots, unavailable.slot_id, clinic.tenant_id, now),
    /no longer available/,
  )
  assert.throws(
    () => createDemoHold(slots, slot.slot_id, 'another-clinic', now),
    /no longer available/,
  )
  assert.throws(
    () =>
      createDemoHold(
        slots,
        slot.slot_id,
        clinic.tenant_id,
        Date.parse(slot.starts_at),
      ),
    /no longer available/,
  )
  const hold = createDemoHold(slots, slot.slot_id, clinic.tenant_id, now)
  assert.equal(hold.status, 'pending_payment')
  assert.equal(holdSeconds(hold, now), 600)
  assert.equal(holdSeconds(hold, Date.parse(hold.hold_expires_at) - 1), 1)
  assert.equal(holdSeconds(hold, Date.parse(hold.hold_expires_at)), 0)
  const near = createDemoHold(
    slots,
    slot.slot_id,
    clinic.tenant_id,
    Date.parse(slot.starts_at) - 60000,
  )
  assert.equal(near.hold_expires_at, slot.starts_at)
  const amount = hold.slot.consultation_price.amount_minor
  slot.consultation_price.amount_minor += 100
  assert.equal(hold.slot.consultation_price.amount_minor, amount)
})

test('picker disables unavailable times and requires an available selection on the current date', () => {
  const slots = demoSlots(clinic, doctors, now)
  const dates = bookingDates(now)
  const slot = slots.find((item) => item.availability === 'available')!
  const props = {
    slots,
    dates,
    date: dates[0],
    selectedId: null,
    onDate: () => {},
    onSelect: () => {},
    onCheckout: () => {},
  }
  const empty = renderToStaticMarkup(createElement(SlotPicker, props))
  assert.match(empty, /Date<select/)
  assert.match(empty, /disabled=""[^>]*>Continue to checkout/)
  assert.match(empty, /Unavailable/)
  const selected = renderToStaticMarkup(
    createElement(SlotPicker, { ...props, selectedId: slot.slot_id }),
  )
  assert.match(selected, /aria-pressed="true"/)
  assert.doesNotMatch(selected, /disabled=""[^>]*>Continue to checkout/)
  const otherDay = renderToStaticMarkup(
    createElement(SlotPicker, {
      ...props,
      date: dates[1],
      selectedId: slot.slot_id,
    }),
  )
  assert.match(otherDay, /disabled=""[^>]*>Continue to checkout/)
  const noSlots = renderToStaticMarkup(
    createElement(SlotPicker, { ...props, slots: [] }),
  )
  assert.match(noSlots, /No available times/)
})

test('checkout shows selected consultation and explicitly stops at preview without payment', () => {
  const slots = demoSlots(clinic, doctors)
  const hold = createDemoHold(
    slots,
    slots.find((slot) => slot.availability === 'available')!.slot_id,
    clinic.tenant_id,
  )
  const markup = renderToStaticMarkup(
    createElement(CheckoutReview, {
      hold,
      clinicName: clinic.name,
      onBack: () => {},
    }),
  )
  assert.match(markup, /Checkout/)
  assert.match(markup, /Local doctor/)
  assert.match(markup, /\$25.00/)
  assert.match(markup, /no payment will be taken/)
  assert.match(markup, /Change time/)
})
