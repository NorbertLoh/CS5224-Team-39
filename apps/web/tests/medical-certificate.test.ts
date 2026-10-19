import assert from 'node:assert/strict'
import { test } from 'node:test'
import { createElement } from 'react'
import { MCFields } from '../src/features/records/MedicalCertificateForm'
import { mcEndDate } from '../src/features/records/medicalCertificate'
import {
  readMedicalCertificate,
  saveMedicalCertificate,
} from '../src/features/records/api'
import { schedulingClient, renderScheduling } from './scheduling-helpers'

test('MC calendar periods are inclusive across months and leap days', () => {
  assert.equal(mcEndDate('2026-10-19', '1'), '2026-10-19')
  assert.equal(mcEndDate('2026-10-31', '2'), '2026-11-01')
  assert.equal(mcEndDate('2028-02-28', '3'), '2028-03-01')
  for (const days of [
    '',
    '0',
    '-1',
    '1.5',
    '2e1',
    'Infinity',
    '999999999999999999',
  ])
    assert.equal(mcEndDate('2026-10-19', days), null)
  assert.equal(mcEndDate('2026-02-30', '1'), null)
  assert.equal(mcEndDate('9999-12-31', '2'), null)
})

test('MC is opt-in and completion seals its form', () => {
  const client = schedulingClient()
  try {
    const initial = renderScheduling(
      client,
      createElement(MCFields, {
        appointmentId: 'appointment',
        draft: null,
        editable: true,
      }),
    )
    assert.match(initial, /Issue MC/)
    assert.doesNotMatch(initial, /type="checkbox"[^>]*checked/)
    assert.doesNotMatch(initial, /MC start date/)
    const finalized = renderScheduling(
      client,
      createElement(MCFields, {
        appointmentId: 'appointment',
        editable: false,
        draft: {
          medical_certificate_id: 'mc',
          appointment_id: 'appointment',
          tenant_id: 'clinic',
          selected: true,
          start_date: '2026-10-31',
          duration_days: 2,
          end_date: '2026-11-01',
          additional_notes: 'Rest',
          issued_at: '2026-10-19T00:00:00Z',
          finalized_at: '2026-10-19T00:00:00Z',
        },
      }),
    )
    assert.match(finalized, /Inclusive end date: 2026-11-01/)
    assert.match(finalized, /MC issued/)
    assert.doesNotMatch(finalized, /Save MC draft/)
  } finally {
    client.clear()
  }
})

test('MC adapter saves only entered fields and rejects a foreign appointment response', async (t) => {
  const client = schedulingClient()
  t.after(() => client.clear())
  const body = {
    selected: true,
    start_date: '2026-10-19',
    duration_days: 1,
    additional_notes: 'Rest',
  }
  t.mock.method(globalThis, 'fetch', async (url: string, init: RequestInit) => {
    assert.equal(
      url,
      '/api/v1/clinical-records/appointments/appointment/medical-certificate',
    )
    assert.equal(init.method, 'PUT')
    assert.deepEqual(JSON.parse(String(init.body)), body)
    return Response.json({ appointment_id: 'appointment', ...body })
  })
  assert.equal(
    (await saveMedicalCertificate('appointment', body)).selected,
    true,
  )
  t.mock.method(globalThis, 'fetch', async () =>
    Response.json({ appointment_id: 'other' }),
  )
  await assert.rejects(readMedicalCertificate('appointment'), /context/)
})
