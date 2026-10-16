import assert from 'node:assert/strict'
import { test } from 'node:test'
import { createElement } from 'react'
import { DoctorRecordForm } from '../src/features/records/DoctorRecordForm'
import { PrescriptionEditor } from '../src/features/records/PrescriptionEditor'
import { RecordWorkspace } from '../src/features/records/RecordWorkspace'
import example from '../../../contracts/examples/prescription-order-quote.json'
import { validItems, prescriptionItems } from '../src/features/records/types'
import {
  catalogue,
  readNote,
  saveNote,
  listPrescriptions,
  appointmentPrescriptions,
  readPrescription,
  savePrescription,
  issuePrescription,
  recordsError,
} from '../src/features/records/api'
import { ApiError } from '../src/lib/api'
import { schedulingClient, renderScheduling } from './scheduling-helpers'

const item = {
  medication_id: 'catalogue-id',
  quantity: 2,
  instructions: '  Synthetic instructions.  ',
}

test('doctor prescription history follows pagination rather than missing an existing live draft', async (context) => {
  const client = schedulingClient()
  let calls = 0
  context.mock.method(globalThis, 'fetch', async () =>
    Response.json({
      items: [
        {
          appointment_id: 'appointment',
          status: ++calls === 1 ? 'voided' : 'draft',
        },
      ],
      next_cursor: calls === 1 ? 'next' : null,
    }),
  )
  try {
    assert.deepEqual(
      (await appointmentPrescriptions('appointment')).map(
        (item) => item.status,
      ),
      ['voided', 'draft'],
    )
  } finally {
    client.clear()
  }
})

test('issued and read-only prescriptions expose no mutation controls; foreign appointment context mounts no clinical forms', () => {
  const client = schedulingClient()
  const prescription = { ...example.prescription, status: 'issued' as const }
  const props = {
    appointmentId: prescription.appointment_id,
    tenantId: prescription.tenant_id,
    token: 's07-test',
    prescription,
    editable: true,
    onFailure: () => {},
  }
  const issued = renderScheduling(
    client,
    createElement(PrescriptionEditor, props),
  )
  assert.match(issued, /content is locked/)
  assert.doesNotMatch(issued, /Add medication|Save draft|>Issue prescription</)
  const completed = renderScheduling(
    client,
    createElement(PrescriptionEditor, {
      ...props,
      editable: false,
      prescription: { ...prescription, status: 'draft' },
    }),
  )
  assert.doesNotMatch(
    completed,
    /Add medication|Save draft|>Issue prescription</,
  )
  client.setQueryData(['records', 'context', 's07-test', 'appointment'], {
    appointment_id: 'appointment',
    doctor_id: 'other-doctor',
  })
  const hidden = renderScheduling(
    client,
    createElement(RecordWorkspace, {
      appointmentId: 'appointment',
      token: 's07-test',
      subjectId: 'doctor',
    }),
  )
  assert.match(hidden, /unavailable to your account/)
  assert.doesNotMatch(hidden, /Consultation note|Prescription|textarea/)
  client.clear()
})
test('prescription input uses catalogue IDs, bounds quantities, and excludes server-owned fields', () => {
  assert.ok(validItems([item]))
  for (const quantity of [0, -1, 1.5, NaN, Infinity, 10001])
    assert.equal(validItems([{ ...item, quantity }]), false)
  for (const items of [
    [],
    [item, item],
    [{ ...item, medication_id: '' }],
    [{ ...item, instructions: ' ' }],
  ])
    assert.equal(validItems(items), false)
  const payload = prescriptionItems([
    {
      ...item,
      display_name: 'Tampered name',
      tenant_id: 'other',
      prescription_item_id: 'invented',
    } as typeof item,
  ])
  assert.deepEqual(payload, [
    {
      medication_id: 'catalogue-id',
      quantity: 2,
      instructions: 'Synthetic instructions.',
    },
  ])
})

test('records adapters use authenticated real routes and exact write bodies', async (context) => {
  const client = schedulingClient()
  const requests: { path: string; init?: RequestInit }[] = []
  context.mock.method(
    globalThis,
    'fetch',
    async (url: string, init?: RequestInit) => {
      requests.push({ path: String(url), init })
      return Response.json({ items: [], next_cursor: null })
    },
  )
  try {
    await saveNote('appointment', ' note ')
    await savePrescription('appointment', undefined, [item])
    await savePrescription('appointment', 'prescription', [item])
    await issuePrescription('prescription')
    await listPrescriptions('appointment', 'cursor value')
    await readPrescription('prescription')
    assert.deepEqual(
      requests
        .slice(0, 4)
        .map(({ path, init }) => [
          path,
          init?.method,
          JSON.parse(String(init?.body)),
        ]),
      [
        [
          '/api/v1/clinical-records/appointments/appointment/note',
          'PUT',
          { text: 'note' },
        ],
        [
          '/api/v1/clinical-records/appointments/appointment/prescriptions',
          'POST',
          { items: prescriptionItems([item]) },
        ],
        [
          '/api/v1/clinical-records/prescriptions/prescription',
          'PATCH',
          { items: prescriptionItems([item]) },
        ],
        [
          '/api/v1/clinical-records/prescriptions/prescription/issue',
          'POST',
          {},
        ],
      ],
    )
    assert.equal(
      new URL(requests[4].path, 'http://localhost').searchParams.get('cursor'),
      'cursor value',
    )
    assert.equal(
      requests[5].path,
      '/api/v1/clinical-records/prescriptions/prescription',
    )
    for (const { init } of requests) {
      assert.equal(
        new Headers(init?.headers).get('Authorization'),
        'Bearer s07-test',
      )
      assert.equal(init?.cache, 'no-store')
    }
  } finally {
    client.clear()
  }
})

test('missing notes are empty; failures are not retried or converted into fabricated success', async (context) => {
  const client = schedulingClient()
  let status = 404
  const fetch = context.mock.method(
    globalThis,
    'fetch',
    async () => new Response('private clinical error', { status }),
  )
  try {
    assert.equal(await readNote('appointment'), null)
    status = 503
    await assert.rejects(
      readNote('appointment'),
      (error) => error instanceof ApiError && error.status === 503,
    )
    await assert.rejects(issuePrescription('prescription'))
    assert.equal(fetch.mock.callCount(), 3)
    assert.match(recordsError(new ApiError(409)), /Reload records/)
    assert.match(recordsError(new ApiError(401)), /sign in again/)
    assert.doesNotMatch(
      recordsError(new Error('private clinical error')),
      /private clinical error/,
    )
    sessionStorage.clear()
    await assert.rejects(saveNote('appointment', 'note'), /Sign in/)
    assert.equal(fetch.mock.callCount(), 3)
  } finally {
    client.clear()
  }
})

test('catalogue collects all pages and rejects foreign tenants and cycling cursors', async (context) => {
  const client = schedulingClient()
  let mode = 'pages'
  let calls = 0
  context.mock.method(globalThis, 'fetch', async () => {
    calls++
    return Response.json({
      items: [
        {
          medication_id: `med-${calls}`,
          tenant_id: mode === 'foreign' ? 'other' : 'clinic',
          active: true,
        },
      ],
      next_cursor:
        mode === 'cycle' || (mode === 'pages' && calls === 1) ? 'next' : null,
    })
  })
  try {
    assert.equal((await catalogue('clinic')).length, 2)
    mode = 'foreign'
    await assert.rejects(catalogue('clinic'), /context/)
    mode = 'cycle'
    await assert.rejects(catalogue('clinic'), /pagination/)
  } finally {
    client.clear()
  }
})

test('doctor workspace shows real appointment selection without synthetic records', () => {
  const client = schedulingClient({
    subject_id: 'doctor',
    global_roles: [],
    memberships: [{ tenant_id: 'clinic', status: 'active', roles: ['doctor'] }],
  })
  client.setQueryData(['records', 'appointments', 's07-test'], {
    pages: [{ items: [], next_cursor: null }],
    pageParams: [null],
  })
  const html = renderScheduling(client, createElement(DoctorRecordForm))
  assert.match(html, /Select an appointment/)
  assert.match(html, /No appointments available/)
  assert.doesNotMatch(html, /Synthetic preview|00000000-0000-4000|Save preview/)
  client.clear()
})
