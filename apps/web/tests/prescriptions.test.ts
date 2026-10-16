import assert from 'node:assert/strict'
import { test } from 'node:test'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { PatientPrescriptions } from '../src/features/records/PatientPrescriptions'
import { PrescriptionDetails } from '../src/features/records/PrescriptionDetails'
import example from '../../../contracts/examples/prescription-order-quote.json'
import type { Prescription } from '../src/features/records/types'
import { schedulingClient, renderScheduling } from './scheduling-helpers'
import { ApiError } from '../src/lib/api'

const prescription = {
  ...example.prescription,
  status: 'issued' as const,
} satisfies Prescription
function patientClient(subjectId: string) {
  return schedulingClient({
    subject_id: subjectId,
    global_roles: ['patient'],
    memberships: [],
  })
}
test('patient refresh failure hides previously cached prescriptions', () => {
  const client = patientClient(prescription.patient_id)
  const queryKey = ['records', 'patient', 's07-test']
  client.setQueryData(queryKey, {
    pages: [{ items: [prescription], next_cursor: null }],
    pageParams: [null],
  })
  client
    .getQueryCache()
    .find({ queryKey })!
    .setState({ status: 'error', error: new ApiError(404) })
  const html = renderScheduling(client, createElement(PatientPrescriptions))
  assert.match(html, /unavailable to your account/)
  assert.doesNotMatch(html, /View details/)
  client.clear()
})
test('patient list renders authenticated server data, pagination and no synthetic scenarios', () => {
  const client = patientClient(prescription.patient_id)
  client.setQueryData(['records', 'patient', 's07-test'], {
    pages: [{ items: [prescription], next_cursor: 'next' }],
    pageParams: [null],
  })
  const html = renderScheduling(client, createElement(PatientPrescriptions))
  assert.match(html, /View details/)
  assert.match(html, /Load more prescriptions/)
  assert.doesNotMatch(
    html,
    /Preview scenario|Synthetic preview|Demo clinic|Download PDF/,
  )
  client.clear()
})
test('patient list excludes records from another patient or cached account', () => {
  const client = patientClient('another-patient')
  client.setQueryData(['records', 'patient', 's07-test'], {
    pages: [{ items: [prescription], next_cursor: null }],
    pageParams: [null],
  })
  let html = renderScheduling(client, createElement(PatientPrescriptions))
  assert.match(html, /No prescriptions available/)
  assert.doesNotMatch(html, /View details/)
  client.removeQueries({ queryKey: ['records', 'patient', 's07-test'] })
  client.setQueryData(['records', 'patient', 'old-session'], {
    pages: [{ items: [prescription], next_cursor: null }],
    pageParams: [null],
  })
  html = renderScheduling(client, createElement(PatientPrescriptions))
  assert.match(html, /Loading prescriptions/)
  assert.doesNotMatch(html, /View details/)
  client.clear()
})
test('prescription detail safely displays server instructions, units and Singapore time', () => {
  const html = renderToStaticMarkup(
    createElement(PrescriptionDetails, {
      prescription: {
        ...prescription,
        items: [
          {
            ...prescription.items[0],
            instructions: '<script>example</script>',
          },
        ],
      },
    }),
  )
  assert.match(html, /2 dispensing units/)
  assert.match(html, /Singapore time/)
  assert.match(html, /11:00/)
  assert.match(html, /&lt;script&gt;example&lt;\/script&gt;/)
  assert.doesNotMatch(html, /<script>/)
})
