import { createElement } from 'react'
import type { ReactElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { Identity } from '../src/features/clinics/api'

export function schedulingClient(identity?: Identity) {
  const values = new Map<string, string>()
  const storage: Storage = {
    get length() {
      return values.size
    },
    clear: () => values.clear(),
    getItem: (key) => values.get(key) ?? null,
    key: (index) => [...values.keys()][index] ?? null,
    removeItem: (key) => {
      values.delete(key)
    },
    setItem: (key, value) => {
      values.set(key, value)
    },
  }
  Object.defineProperty(globalThis, 'sessionStorage', {
    value: storage,
    configurable: true,
  })
  storage.setItem(
    'telelink.session',
    JSON.stringify({
      accessToken: 's07-test',
      refreshToken: 'refresh',
      expiresAt: Date.now() + 3600000,
    }),
  )
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: Infinity } },
  })
  if (identity) client.setQueryData(['identity', 's07-test'], identity)
  return client
}
export function renderScheduling(client: QueryClient, element: ReactElement) {
  return renderToStaticMarkup(
    createElement(QueryClientProvider, { client }, element),
  )
}
