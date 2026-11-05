import assert from 'node:assert/strict'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { DocumentResults } from '../src/features/documents/DocumentList'
import { pastDocumentGroups } from '../src/features/documents/pastDocumentGroups'
import { previousVisitDocuments } from '../src/features/documents/previousVisitDocuments'
import { documentDownloadUrl } from '../src/features/documents/api'
import type { DocumentMetadata } from '../src/features/documents/types'
import type { Appointment } from '../src/features/scheduling/api'

const anchor = {
  appointment_id: 'current',
  tenant_id: 'clinic',
  patient_id: 'patient',
  starts_at: '2026-11-05T01:00:00Z',
} as Appointment
const old = {
  ...anchor,
  appointment_id: 'old',
  doctor_id: 'doctor',
  doctor_name: 'Doctor A',
  starts_at: '2026-11-01T01:00:00Z',
  status: 'completed',
} as Appointment
const recent = {
  ...old,
  appointment_id: 'recent',
  starts_at: '2026-11-03T01:00:00Z',
} as Appointment
function document(
  id: string,
  visit: Appointment,
  kind: DocumentMetadata['kind'],
  created = '2026-11-04T01:00:00Z',
): DocumentMetadata {
  return {
    document_id: id,
    tenant_id: visit.tenant_id,
    appointment_id: visit.appointment_id,
    kind,
    created_at: created,
    updated_at: created,
    status: 'ready',
    prescription_id: null,
    payment_id: null,
    medical_certificate_id: null,
  }
}
const prescription = document('prescription', old, 'prescription_pdf')
const receipt = document('receipt', old, 'receipt_pdf')
const certificate = document(
  'mc',
  recent,
  'medical_certificate_pdf',
  '2026-11-03T02:00:00Z',
)
const groups = pastDocumentGroups(
  [receipt, prescription, certificate, prescription],
  [old, recent, old],
)
assert.equal(groups.length, 2)
assert.equal(groups[0].visit.appointment_id, 'recent')
assert.deepEqual(
  groups[1].documents.map((row) => row.document_id),
  ['prescription', 'receipt'],
)

function render(items: DocumentMetadata[], visits = [old, recent]) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  client.setQueryData(
    [
      'documents',
      'token',
      'scope',
      null,
      'clinic',
      'current',
      'patient',
      anchor.starts_at,
    ],
    {
      pages: [{ items, visits, next_cursor: null }],
      pageParams: [null],
    },
  )
  const html = renderToStaticMarkup(
    createElement(
      QueryClientProvider,
      { client },
      createElement(DocumentResults, {
        role: 'doctor',
        variant: 'past',
        previousVisitsFor: anchor,
        tenantId: 'clinic',
        token: 'token',
        scope: 'scope',
      }),
    ),
  )
  client.clear()
  return html
}
const html = render([prescription, receipt, certificate])
assert.equal((html.match(/Consultation ·/g) ?? []).length, 2)
assert(html.indexOf('3 Nov 2026') < html.indexOf('1 Nov 2026'))
assert(html.includes('2 documents') && html.includes('1 document'))
assert(html.includes('Prescription, Receipt'))
assert(html.includes('Doctor A'))
assert(!html.includes('Download PDF'), 'consultation groups start collapsed')
assert(render([]).includes('No documents from previous consultations.'))
assert(
  render([{ ...prescription, tenant_id: 'wrong' }]).includes(
    'These documents are unavailable to your account.',
  ),
)

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
  const calls: URL[] = []
  globalThis.fetch = async (input) => {
    const url = new URL(String(input), 'https://example.test')
    calls.push(url)
    if (url.pathname.includes('/scheduling/'))
      return Response.json({
        items: [old, recent],
        next_cursor: 'older-visits',
      })
    if (url.pathname.endsWith('/download'))
      return new Response('%PDF-1.4 test', {
        headers: { 'Content-Type': 'application/pdf' },
      })
    if (url.searchParams.get('appointment_id') === 'recent')
      return Response.json({ items: [certificate], next_cursor: null })
    return url.searchParams.has('cursor')
      ? Response.json({ items: [receipt], next_cursor: null })
      : Response.json({ items: [prescription], next_cursor: 'document-page2' })
  }
  const page = await previousVisitDocuments(
    anchor,
    null,
    new AbortController().signal,
  )
  assert.equal(page.items.length, 3)
  assert.deepEqual(page.visits, [old, recent])
  assert.equal(page.next_cursor, 'older-visits')
  assert(
    calls.every((url) => url.searchParams.get('history_for') === 'current'),
  )
  assert(
    calls.some((url) => url.searchParams.get('cursor') === 'document-page2'),
  )
  const blob = await documentDownloadUrl('prescription', undefined, 'current')
  assert(blob.startsWith('blob:'))
  URL.revokeObjectURL(blob)
  assert.equal(calls.at(-1)?.searchParams.get('history_for'), 'current')
} finally {
  globalThis.fetch = nativeFetch
  if (storage) Object.defineProperty(globalThis, 'localStorage', storage)
  else delete (globalThis as Record<string, unknown>).localStorage
}
console.log(
  'PASS: consultation grouping, actual visit chronology, merged/deduplicated PDFs, collapsed summaries, scope rejection, historical pagination and PDF download scoping.',
)
