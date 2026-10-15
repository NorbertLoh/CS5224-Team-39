import assert from 'node:assert/strict'
import { test } from 'node:test'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { DoctorRecordForm } from '../src/features/records/DoctorRecordForm'
import { draftPrescription, validItems } from '../src/features/records/fixtures'

test('free-text prescription inputs accept names and reject empty names, invalid quantities and duplicate items', () => {
  const item = { display_name: '  Synthetic medication A  ', quantity: 2, instructions: 'Synthetic placeholder.' }
  assert.ok(validItems([item]))
  for (const quantity of [0, -1, 1.5, NaN, Infinity]) assert.equal(validItems([{ ...item, quantity }]), false)
  assert.equal(validItems([]), false)
  assert.equal(validItems([{ ...item, display_name: '  ' }]), false)
  assert.equal(validItems([{ ...item, instructions: '  ' }]), false)
  assert.equal(validItems([item, item]), false)
  assert.equal(validItems([item, { ...item, display_name: 'synthetic medication a' }]), false)
  assert.ok(validItems([item, { ...item, display_name: 'Synthetic medication B' }]))
  const draft = draftPrescription([item])
  assert.equal(draft.status, 'draft')
  assert.equal(draft.issued_at, null)
  assert.equal(draft.items[0].display_name, 'Synthetic medication A')
  assert.equal('medication_id' in draft.items[0], false)
  assert.equal('unit_price' in draft.items[0], false)
})

test('doctor preview exposes its appointment context and temporary-save limitation', () => {
  const html = renderToStaticMarkup(createElement(DoctorRecordForm))
  assert.match(html, /Synthetic preview/)
  assert.match(html, /No clinical record is created/)
  assert.match(html, /Consultation note/)
  assert.match(html, /Issue preview prescription/)
  assert.match(html, /No medications added/)
})
