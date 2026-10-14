import assert from 'node:assert/strict'
import { test } from 'node:test'
import { QueryClient, QueryObserver } from '@tanstack/react-query'
import { refreshClinicViews } from '../src/features/clinics/cache'

test('clinic saves refresh mounted views and mark unmounted clinic views stale', async () => {
  const client = new QueryClient({ defaultOptions: { queries: { staleTime: Infinity, retry: false } } })
  const publicKey = ['public-clinic', 'example']
  client.setQueryData(publicKey, { name: 'Before save' })
  client.setQueryData(['managed-clinics', 'session', ['clinic']], [{ name: 'Before save' }])
  client.setQueryData(['platform-clinic', 'session', 'clinic'], { name: 'Before save' })
  client.setQueryData(['clinic-profile', 'session', 'clinic'], { name: 'Before save' })
  client.setQueryData(['identity', 'session'], { subject_id: 'user' })
  const observer = new QueryObserver(client, {
    queryKey: publicKey, queryFn: async () => ({ name: 'Persisted name' }),
  })
  const unsubscribe = observer.subscribe(() => {})
  try {
    await refreshClinicViews(client)
    assert.deepEqual(client.getQueryData(publicKey), { name: 'Persisted name' })
    for (const key of ['managed-clinics', 'platform-clinic', 'clinic-profile']) {
      assert.equal(client.getQueryCache().find({ queryKey: [key], exact: false })?.isStale(), true)
    }
    assert.equal(client.getQueryCache().find({ queryKey: ['identity'], exact: false })?.isStale(), false)
  } finally { unsubscribe(); client.clear() }
})
