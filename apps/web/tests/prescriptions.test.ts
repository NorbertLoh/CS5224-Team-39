import assert from 'node:assert/strict'
import { test } from 'node:test'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { PatientPrescriptions, PrescriptionDetails } from '../src/features/records/PatientPrescriptions'
import { prescriptionFixture } from '../src/features/records/fixtures'

test('patient preview identifies fixtures and offers empty and unavailable scenarios', () => {
  const html = renderToStaticMarkup(createElement(PatientPrescriptions))
  assert.match(html, /independent of your account/)
  assert.match(html, /No prescriptions/)
  assert.match(html, /Prescription unavailable/)
  assert.match(html, /View details/)
  assert.doesNotMatch(html, /Download PDF/)
})

test('prescription detail safely displays instructions, units and Singapore issue time', () => {
  const html = renderToStaticMarkup(createElement(PrescriptionDetails, { prescription: { ...prescriptionFixture, status: 'issued', items: [{ ...prescriptionFixture.items[0], instructions: '<script>example</script>' }] } }))
  assert.match(html, /2 dispensing units/)
  assert.match(html, /Singapore time/)
  assert.match(html, /11:00/)
  assert.match(html, /&lt;script&gt;example&lt;\/script&gt;/)
  assert.doesNotMatch(html, /<script>/)
})
