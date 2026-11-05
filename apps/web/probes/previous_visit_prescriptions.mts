import assert from 'node:assert/strict'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { appointmentPrescriptions } from '../src/features/records/api/prescriptions'
import { PreviousVisitPrescriptions } from '../src/features/records/notes/PreviousVisitPrescriptions'
import type { Prescription } from '../src/features/records/types'
import type { Appointment } from '../src/features/scheduling/api'

const visit = {
  appointment_id: 'old-visit',
  patient_id: 'patient',
  tenant_id: 'clinic',
  doctor_id: 'previous-doctor',
} as Appointment
const issued = {
  ...visit,
  prescription_id: 'issued',
  status: 'issued',
  issued_at: '2026-11-01T01:00:00Z',
  items: [
    {
      prescription_item_id: 'item',
      medication_id: 'medicine',
      display_name: 'Medicine <name>',
      quantity: 5,
      instructions: 'Take with food.',
    },
  ],
} as Prescription
const voided = {
  ...issued,
  prescription_id: 'old',
  status: 'voided',
} as Prescription
const key = [
  'records',
  'previous-prescriptions',
  'token',
  visit.appointment_id,
  'current-visit',
]

function render(data?: Prescription[], error?: Error) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, retryOnMount: false } },
  })
  if (data) client.setQueryData(key, data)
  if (error) {
    client
      .getQueryCache()
      .build(client, { queryKey: key })
      .setState({ status: 'error', error })
  }
  const html = renderToStaticMarkup(
    createElement(
      QueryClientProvider,
      { client },
      createElement(PreviousVisitPrescriptions, {
        visit,
        token: 'token',
        historyFor: 'current-visit',
      }),
    ),
  )
  client.clear()
  return html
}
const html = render([issued, voided])
assert(html.includes('Issued prescription'))
assert(html.includes('Voided prescription'))
assert(html.includes('This prescription is no longer valid.'))
assert(html.includes('Medicine &lt;name&gt;'))
assert(html.includes('Quantity: 5'))
assert(html.includes('Take with food.'))
assert(!html.includes('<input') && !html.includes('<textarea'))
assert(render([]).includes('No issued prescriptions for this visit.'))
assert(render([{ ...issued, items: [] }]).includes('No medicines prescribed.'))
assert(render().includes('Loading previous prescriptions...'))
assert(render(undefined, new Error('unavailable')).includes('Try again'))

const nativeFetch = globalThis.fetch
const storage = Object.getOwnPropertyDescriptor(globalThis, 'localStorage')
Object.defineProperty(globalThis, 'localStorage', {
  configurable: true,
  value: {
    getItem: () =>
      JSON.stringify({
        accessToken: 'token',
        refreshToken: 'refresh',
        expiresAt: Date.now() + 3600000,
      }),
  },
})
try {
  const requests: URL[] = []
  globalThis.fetch = async (input) => {
    const url = new URL(String(input), 'https://example.test')
    requests.push(url)
    return Response.json({
      items: [requests.length === 1 ? issued : voided],
      next_cursor: requests.length === 1 ? 'page2' : null,
    })
  }
  const rows = await appointmentPrescriptions(
    visit.appointment_id,
    undefined,
    'current-visit',
  )
  assert.equal(rows.length, 2)
  assert(
    requests.every(
      (url) => url.searchParams.get('history_for') === 'current-visit',
    ),
  )
  assert(
    requests.every(
      (url) => url.searchParams.get('appointment_id') === visit.appointment_id,
    ),
  )
  assert.equal(requests[1].searchParams.get('cursor'), 'page2')
  globalThis.fetch = async () =>
    Response.json({
      items: [{ ...issued, appointment_id: 'wrong' }],
      next_cursor: null,
    })
  await assert.rejects(
    appointmentPrescriptions(visit.appointment_id, undefined, 'current-visit'),
    /Invalid prescription context/,
  )
} finally {
  globalThis.fetch = nativeFetch
  if (storage) Object.defineProperty(globalThis, 'localStorage', storage)
  else delete (globalThis as Record<string, unknown>).localStorage
}
console.log(
  'PASS: read-only history prescriptions, issued/voided/empty/loading/error states, escaped content, history-scoped pagination and mismatched visit rejection.',
)
