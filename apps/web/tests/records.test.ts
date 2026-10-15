import assert from 'node:assert/strict'
import { test } from 'node:test'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { DoctorRecordForm } from '../src/features/records/DoctorRecordForm'
import { catalogue, draftPrescription, validItems } from '../src/features/records/fixtures'

test('prescription inputs reject catalogue tampering, invalid quantities and duplicate items', () => {
  const item = { medication_id: catalogue[0].medication_id, quantity: 2, instructions: 'Synthetic placeholder.' }
  assert.ok(validItems([item]))
  for (const quantity of [0, -1, 1.5, NaN, Infinity]) assert.equal(validItems([{ ...item, quantity }]), false)
  assert.equal(validItems([]), false)
  assert.equal(validItems([{ ...item, medication_id: 'untrusted-id' }]), false)
  assert.equal(validItems([{ ...item, instructions: '  ' }]), false)
  assert.equal(validItems([item, item]), false)
  const draft = draftPrescription([item])
  assert.equal(draft.status, 'draft')
  assert.equal(draft.issued_at, null)
  assert.equal(draft.items[0].display_name, catalogue[0].display_name)
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
