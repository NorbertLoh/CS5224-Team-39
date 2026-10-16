/** Real R04 adapters through Vite; run check_records_frontend.py. */
import assert from 'node:assert/strict'
import {
  catalogue,
  readNote,
  saveNote,
  listPrescriptions,
  readPrescription,
  savePrescription,
  issuePrescription,
} from '../apps/web/src/features/records/api'
import { listAppointments } from '../apps/web/src/features/scheduling/api'
import { ApiError } from '../apps/web/src/lib/api'

const run = JSON.parse(process.env.R04_CONTEXT ?? '{}')
assert.ok(
  run.appointment && run.tokens && run.medication && run.web,
  'Run the Python driver',
)
const nativeFetch = globalThis.fetch
globalThis.fetch = (input, init) => {
  assert.equal(typeof input, 'string')
  assert.ok(String(input).startsWith('/api/v1/'))
  return nativeFetch(`${run.web}${input}`, init)
}
const values = new Map<string, string>()
Object.defineProperty(globalThis, 'sessionStorage', {
  value: {
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => values.set(key, value),
    removeItem: (key: string) => values.delete(key),
  },
})
function signIn(role: string) {
  const token = run.tokens[role]
  values.set(
    'telelink.session',
    JSON.stringify({
      accessToken: token.access_token,
      refreshToken: token.refresh_token,
      expiresAt: Date.now() + 1800000,
    }),
  )
}
const denied = (status: number) => (error: unknown) =>
  error instanceof ApiError && error.status === status
signIn('doctor')
assert.ok(
  (await listAppointments(run.tenant)).items.some(
    (item) => item.appointment_id === run.appointment,
  ),
)
if (run.phase === 'completed') {
  assert.ok(await readNote(run.appointment))
  await assert.rejects(
    saveNote(run.appointment, 'Late synthetic note'),
    denied(409),
  )
  console.log('PASS: completed appointment is readable and rejects writes.')
} else {
  assert.ok(
    (await catalogue(run.tenant)).some(
      (item) => item.medication_id === run.medication,
    ),
  )
  assert.equal(await readNote(run.appointment), null)
  const note = await saveNote(run.appointment, 'R04 synthetic note')
  assert.equal((await readNote(run.appointment))?.note_id, note.note_id)
  const items = [
    {
      medication_id: run.medication,
      quantity: 2,
      instructions: 'R04 synthetic instructions',
    },
  ]
  const draft = await savePrescription(run.appointment, undefined, items)
  assert.equal(draft.status, 'draft')
  assert.equal(
    draft.items[0].display_name,
    'R04 synthetic catalogue medication',
  )
  assert.equal(
    (
      await savePrescription(run.appointment, draft.prescription_id, [
        { ...items[0], quantity: 3 },
      ])
    ).items[0].quantity,
    3,
  )
  const issued = await issuePrescription(draft.prescription_id)
  assert.equal(issued.status, 'issued')
  assert.equal(
    (await issuePrescription(draft.prescription_id)).issued_at,
    issued.issued_at,
  )
  assert.equal(
    (await readPrescription(draft.prescription_id)).items[0].quantity,
    3,
  )
  await assert.rejects(
    savePrescription(run.appointment, draft.prescription_id, items),
    denied(409),
  )
  signIn('patient')
  assert.ok(
    (await listPrescriptions(run.appointment)).items.some(
      (item) => item.prescription_id === draft.prescription_id,
    ),
  )
  assert.equal(
    (await readPrescription(draft.prescription_id)).patient_id,
    run.patient,
  )
  await assert.rejects(saveNote(run.appointment, 'Unauthorized'), denied(404))
  for (const role of ['clinic', 'platform']) {
    signIn(role)
    await assert.rejects(readPrescription(draft.prescription_id), denied(404))
  }
  values.clear()
  await assert.rejects(readPrescription(draft.prescription_id), /Sign in/)
  for (const path of [
    '/api/v1/clinical-records/internal/probe',
    '/api/v1/fulfilment/internal/probe',
    '/api/v1/clinical-records/%69nternal/probe',
    '/api/v1/fulfilment/%69nternal/probe',
  ]) {
    const response = await nativeFetch(`${run.web}${path}`)
    assert.equal(response.status, 404)
    assert.ok(
      !response.headers.get('content-type')?.includes('application/json'),
      'Vite must block internal routes before reaching FastAPI',
    )
  }
  console.log(
    'PASS: real scheduling/catalogue/records adapters through Vite; durable note/draft/reload/issue, issued lock, patient reads, role denial and internal ingress exclusion.',
  )
}
