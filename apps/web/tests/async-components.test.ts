import assert from 'node:assert/strict'
import { test } from 'node:test'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { QueryClientProvider, useQueryClient } from '@tanstack/react-query'
import { ErrorState } from '../src/components/ErrorState'
import { LoadingState } from '../src/components/LoadingState'
import { ApiError } from '../src/lib/api-client'
import { createQueryClient } from '../src/lib/query-client'

test('loading state announces progress and honors reduced motion', () => {
  const markup = renderToStaticMarkup(createElement(LoadingState, { message: 'Loading appointments…' }))
  assert.match(markup, /role="status"/)
  assert.match(markup, /aria-busy="true"/)
  assert.match(markup, /Loading appointments/)
  assert.match(markup, /motion-reduce:animate-none/)
})

test('error state hides arbitrary exception text and cancellation; retry is optional', () => {
  const markup = renderToStaticMarkup(createElement(ErrorState, { error: new Error('SECRET stack trace') }))
  assert.match(markup, /role="alert"/)
  assert.doesNotMatch(markup, /SECRET|<button/)
  assert.equal(renderToStaticMarkup(createElement(ErrorState, { error: new DOMException('Cancelled', 'AbortError') })), '')
})

test('structured error displays safe correlation and disables a running retry', () => {
  const markup = renderToStaticMarkup(createElement(ErrorState, {
    error: new ApiError('Please try again.', { kind: 'http', method: 'GET', code: 'unavailable', status: 503, requestId: 'synthetic-ref' }),
    onRetry: () => {}, retrying: true,
  }))
  assert.match(markup, /Reference: synthetic-ref/)
  assert.match(markup, /disabled=""/)
  assert.match(markup, /Retrying/)
})

test('provider makes the shared client available to feature components', () => {
  const client = createQueryClient()
  function Consumer() {
    assert.equal(useQueryClient(), client)
    return createElement(LoadingState)
  }
  try {
    assert.match(renderToStaticMarkup(createElement(QueryClientProvider, { client }, createElement(Consumer))), /Loading/)
  } finally {
    client.clear()
  }
})
