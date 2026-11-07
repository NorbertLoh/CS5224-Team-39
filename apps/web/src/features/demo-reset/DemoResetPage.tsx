import { accessToken } from '@/auth/access-token'
import { ErrorState } from '@/components/ErrorState'
import { Button } from '@/components/ui/button'
import { ApiError, apiFetch } from '@/lib/api'
import { WorkspacePage } from '@/navigation/WorkspacePage'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useRef, useState } from 'react'

type ResetState = {
  environment?: 'local' | 'demo'
  status: 'ready' | 'queued' | 'running' | 'succeeded' | 'failed'
  request_id?: string
  stage?: string
  updated_at?: string
}

async function resetRequest(body?: { request_id: string; confirmation: string }): Promise<ResetState> {
  return (await apiFetch('/identity/demo-reset', {
    accessToken: await accessToken(),
    ...(body ? {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    } : {}),
  })).json()
}

export function DemoResetPage() {
  const client = useQueryClient()
  const [confirmation, setConfirmation] = useState('')
  const [error, setError] = useState('')
  const requestId = useRef<string | null>(null)
  const query = useQuery({
    queryKey: ['demo-reset'], queryFn: () => resetRequest(),
    refetchInterval: 5000, retry: false,
  })
  const mutation = useMutation({
    mutationFn: () => {
      requestId.current ??= crypto.randomUUID()
      return resetRequest({ request_id: requestId.current, confirmation: 'RESET DEMO' })
    },
    onSuccess: (state) => {
      client.setQueryData(['demo-reset'], state)
      setError('')
      setConfirmation('')
    },
    onError: (failure) => {
      setError(failure instanceof ApiError && failure.status === 409
        ? 'A reset is already running. Its progress will appear here.'
        : 'Could not confirm the reset request. Use Retry request to safely check the same request.')
      void query.refetch()
    },
  })
  const state = query.data
  const busy = mutation.isPending || state?.status === 'queued' || state?.status === 'running'
  const unavailable = query.error instanceof ApiError && query.error.status === 404
  const denied = query.error instanceof ApiError && query.error.status === 403
  const terminal = state?.status === 'succeeded' || state?.status === 'failed'
  const local = state?.environment === 'local'

  return <WorkspacePage title={local ? 'Reset local demo data' : 'Reset demo data'}>
    <section className="mt-6 max-w-2xl space-y-5 rounded-xl border bg-white p-6">
      {local && <p className="font-medium">Target: local demo data</p>}
      <p>Restore the five seed accounts, Meridian Health Partners’ pending clinic application,
        and Dr. Tan’s pending doctor application with sample licence evidence and clinic assignment.</p>
      <p className="text-sm text-slate-600">This removes demo appointments, payments, prescriptions,
        documents and other saved application data. Existing login passwords are preserved.
        No backup is created.
        No real payment is refunded or delivery cancelled. The demo will be temporarily unavailable.</p>
      {unavailable ? <p>Reset is not enabled in this environment.</p>
        : denied ? <p>Sign in as platform@example.test to reset the demo.</p>
        : <>
          <div aria-live="polite" role="status" className="rounded-lg bg-slate-50 p-4">
            {state?.status === 'succeeded' ? 'Demo reset complete. Both applications are pending review.'
              : state?.status === 'failed' ? 'The reset needs attention. See the operator recovery instructions before retrying.'
                : state?.stage ?? (query.isPending ? 'Checking reset availability…' : 'Ready to reset the demo.')}
            {query.isError && state && <p className="mt-2 text-sm">Waiting for the demo to reconnect. Keep this page open; progress checks continue automatically.</p>}
          </div>
          {query.isError && !state && <ErrorState message="Could not check reset availability." onRetry={() => void query.refetch()} />}
          {error && <ErrorState message={error} />}
          {state?.status === 'queued' && <Button disabled={mutation.isPending} onClick={() => {
            requestId.current = state.request_id ?? null
            mutation.mutate()
          }}>Retry request</Button>}
          {error && requestId.current && !busy && <Button disabled={mutation.isPending} onClick={() => mutation.mutate()}>Retry request</Button>}
          {!busy && state && <form onSubmit={(event) => {
            event.preventDefault()
            if (confirmation !== 'RESET DEMO') return
            if (terminal) requestId.current = null
            mutation.mutate()
          }} className="space-y-3">
            <label htmlFor="reset-confirmation" className="block font-medium">Type RESET DEMO to confirm</label>
            <input id="reset-confirmation" autoComplete="off" value={confirmation}
              onChange={(event) => setConfirmation(event.target.value)}
              className="w-full rounded-md border px-3 py-2" />
            <Button type="submit" variant="destructive" disabled={confirmation !== 'RESET DEMO' || query.isError}>{local ? 'Reset local data' : 'Reset demo data'}</Button>
          </form>}
          {state?.status === 'succeeded' && <a className="block underline" href="/platform-admin/clinics">Review clinic applications</a>}
        </>}
    </section>
  </WorkspacePage>
}
