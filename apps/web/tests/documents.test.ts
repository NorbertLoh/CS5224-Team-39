import assert from 'node:assert/strict'
import { test } from 'node:test'
import { createElement } from 'react'
import {
  DocumentList,
  DocumentResults,
} from '../src/features/documents/DocumentList'
import { DocumentRow } from '../src/features/documents/DocumentRow'
import type { DocumentMetadata } from '../src/features/documents/types'
import {
  listDocuments,
  documentDownloadUrl,
  validateDownload,
  documentsError,
} from '../src/features/documents/api'
import { ApiError } from '../src/lib/api'
import { schedulingClient, renderScheduling } from './scheduling-helpers'

const document: DocumentMetadata = {
  document_id: 'document-id',
  tenant_id: 'clinic',
  appointment_id: 'appointment',
  prescription_id: 'prescription',
  payment_id: null,
  medical_certificate_id: null,
  kind: 'prescription_pdf',
  status: 'ready',
  created_at: '2026-10-16T02:00:00Z',
  updated_at: '2026-10-16T02:00:00Z',
}

test('document list forwards bearer token, appointment filter and cursor with no-store', async (context) => {
  const client = schedulingClient()
  context.mock.method(
    globalThis,
    'fetch',
    async (input: string | URL | Request, init?: RequestInit) => {
      const url = new URL(String(input), 'http://localhost')
      assert.equal(url.pathname, '/api/v1/document/documents')
      assert.equal(url.searchParams.get('appointment_id'), 'appointment')
      assert.equal(url.searchParams.get('cursor'), 'cursor+value')
      assert.equal(
        new Headers(init?.headers).get('Authorization'),
        'Bearer s07-test',
      )
      assert.equal(init?.cache, 'no-store')
      assert.ok(init?.signal)
      return Response.json({ items: [document], next_cursor: null })
    },
  )
  try {
    assert.equal(
      (await listDocuments('appointment', 'cursor+value')).items[0].document_id,
      'document-id',
    )
  } finally {
    client.clear()
  }
})

test('document adapter rejects another appointment and downloads fetch fresh signed URLs', async (context) => {
  const client = schedulingClient()
  let count = 0
  context.mock.method(
    globalThis,
    'fetch',
    async (input: string | URL | Request) => {
      if (String(input).includes('/download')) {
        assert.match(String(input), /id%2Fvalue\/download$/)
        return Response.json({
          download_url: `https://bucket.test/file?signature=${++count}`,
          expires_at: new Date(Date.now() + 120000).toISOString(),
        })
      }
      return Response.json({ items: [document], next_cursor: null })
    },
  )
  try {
    await assert.rejects(listDocuments('other-appointment'), /context/)
    assert.notEqual(
      await documentDownloadUrl('id/value'),
      await documentDownloadUrl('id/value'),
    )
    assert.equal(count, 2)
  } finally {
    client.clear()
  }
})

test('download validation rejects executable, insecure, credentialed and expired links', () => {
  const expires_at = new Date(Date.now() + 120000).toISOString()
  for (const download_url of [
    'javascript:alert(1)',
    'data:text/html,test',
    'http://evil.test/file',
    'https://user:pass@bucket.test/file',
    'https://bucket.test/file#fragment',
  ]) {
    assert.throws(() => validateDownload({ download_url, expires_at }))
  }
  for (const expiry of ['invalid', '2000-01-01T00:00:00Z'])
    assert.throws(() =>
      validateDownload({
        download_url: 'https://bucket.test/file',
        expires_at: expiry,
      }),
    )
  assert.throws(() =>
    validateDownload(
      { download_url: 'http://localhost:4566/file', expires_at },
      true,
    ),
  )
  assert.equal(
    validateDownload({
      download_url: 'http://localhost:4566/file?signature=test',
      expires_at,
    }),
    'http://localhost:4566/file?signature=test',
  )
})

test('pending and failed documents expose no download action; ready PDF is accessible', () => {
  const client = schedulingClient()
  try {
    for (const status of ['pending', 'failed'] as const) {
      const html = renderScheduling(
        client,
        createElement(DocumentRow, { document: { ...document, status } }),
      )
      assert.doesNotMatch(html, /<button|href=/)
      assert.match(
        html,
        status === 'pending' ? /Preparing PDF/ : /PDF unavailable/,
      )
    }
    const ready = renderScheduling(
      client,
      createElement(DocumentRow, { document }),
    )
    assert.match(ready, /aria-label="Download Prescription PDF"/)
    assert.match(ready, /10:00 am SGT/)
    assert.doesNotMatch(ready, /https?:|signature|storage_key/)
  } finally {
    client.clear()
  }
})

test('document results show pagination and empty states and conceal wrong clinic metadata', () => {
  const client = schedulingClient()
  const props = {
    role: 'patient' as const,
    token: 's07-test',
    scope: 'patient',
    appointmentId: 'appointment',
    tenantId: 'clinic',
  }
  const key = ['documents', 's07-test', 'patient', 'appointment', 'clinic']
  try {
    client.setQueryData(key, {
      pages: [{ items: [document], next_cursor: 'next' }],
      pageParams: [null],
    })
    assert.match(
      renderScheduling(client, createElement(DocumentResults, props)),
      /Load more documents/,
    )
    client.setQueryData(key, {
      pages: [{ items: [], next_cursor: null }],
      pageParams: [null],
    })
    assert.match(
      renderScheduling(client, createElement(DocumentResults, props)),
      /No documents available yet/,
    )
    client.setQueryData(key, {
      pages: [
        { items: [{ ...document, tenant_id: 'foreign' }], next_cursor: null },
      ],
      pageParams: [null],
    })
    const hidden = renderScheduling(
      client,
      createElement(DocumentResults, props),
    )
    assert.match(hidden, /unavailable to your account/)
    assert.doesNotMatch(hidden, /Download PDF|document-id/)
  } finally {
    client.clear()
  }
})

test('document UI requires current roles and does not reuse another token cache', () => {
  const client = schedulingClient({
    subject_id: 'admin',
    global_roles: ['platform_admin'],
    memberships: [],
  })
  try {
    assert.match(
      renderScheduling(
        client,
        createElement(DocumentList, { role: 'patient' }),
      ),
      /unavailable to your account/,
    )
    assert.match(
      renderScheduling(
        client,
        createElement(DocumentResults, {
          role: 'patient',
          token: 'other-token',
          scope: 'other',
        }),
      ),
      /Loading documents/,
    )
  } finally {
    client.clear()
  }
})

test('failed access refresh hides previously cached document metadata and actions', async () => {
  const client = schedulingClient()
  const queryKey = ['documents', 's07-test', 'patient', null, null]
  client.setQueryData(queryKey, {
    pages: [{ items: [document], next_cursor: null }],
    pageParams: [null],
  })
  try {
    await assert.rejects(
      client.fetchInfiniteQuery({
        queryKey,
        initialPageParam: null,
        queryFn: async () => {
          throw new ApiError(404)
        },
      }),
    )
    const html = renderScheduling(
      client,
      createElement(DocumentResults, {
        role: 'patient',
        token: 's07-test',
        scope: 'patient',
      }),
    )
    assert.match(html, /unavailable to your account/)
    assert.doesNotMatch(html, /document-id|Download PDF/)
  } finally {
    client.clear()
  }
})

test('document failures provide safe authentication, not-ready and pagination feedback', () => {
  assert.match(documentsError(new ApiError(401)), /sign in again/)
  assert.match(documentsError(new ApiError(404)), /unavailable to your account/)
  assert.match(documentsError(new ApiError(409)), /not ready/)
  assert.match(documentsError(new ApiError(422)), /Refresh documents/)
  assert.doesNotMatch(
    documentsError(new Error('secret URL or provider body')),
    /secret|provider/,
  )
})
