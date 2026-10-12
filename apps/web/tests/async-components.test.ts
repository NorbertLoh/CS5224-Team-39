import assert from 'node:assert/strict'
import { test } from 'node:test'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { QueryClientProvider, useQueryClient } from '@tanstack/react-query'
import { ErrorState } from '../src/components/ErrorState'
import { LoadingState } from '../src/components/LoadingState'
import { queryClient } from '../src/lib/query-client'

test('loading state announces progress and honors reduced motion', () => {
  const markup = renderToStaticMarkup(createElement(LoadingState, { message: 'Loading appointments…' }))
  assert.match(markup, /role="status"/)
  assert.match(markup, /aria-busy="true"/)
  assert.match(markup, /Loading appointments/)
  assert.match(markup, /motion-reduce:animate-none/)
})

test('error state has a safe default message; retry is optional', () => {
  const markup = renderToStaticMarkup(createElement(ErrorState))
  assert.match(markup, /role="alert"/)
  assert.doesNotMatch(markup, /SECRET|<button/)
})

test('error state displays a supplied message and disables a running retry', () => {
  const markup = renderToStaticMarkup(createElement(ErrorState, {
    message: 'Could not load appointments.',
    onRetry: () => {}, retrying: true,
  }))
  assert.match(markup, /Could not load appointments/)
  assert.match(markup, /disabled=""/)
  assert.match(markup, /Retrying/)
})

test('provider makes the shared client available to feature components', () => {
  const client = queryClient
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
