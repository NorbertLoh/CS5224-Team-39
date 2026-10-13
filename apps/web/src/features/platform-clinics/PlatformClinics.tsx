import { useState } from 'react'
import { useInfiniteQuery, useQuery, useQueryClient } from '@tanstack/react-query'
import { AuthControls } from '@/auth/AuthControls'
import { readSession } from '@/auth/session'
import { Button } from '@/components/ui/button'
import { ErrorState } from '@/components/ErrorState'
import { LoadingState } from '@/components/LoadingState'
import { ApiError } from '@/lib/api'
import { currentIdentity } from '../clinics/api'
import { listAdminClinics, reviewClinic, saveCommission } from './api'
import type { AdminClinic, ReviewDecision } from './api'

const statuses = { pending_review: 'Pending review', active: 'Active', rejected: 'Rejected', suspended: 'Suspended' }

export function PlatformClinics() {
  const [session, setSession] = useState(readSession)
  return <div className="min-h-screen bg-slate-50 text-slate-900">
    <header className="border-b bg-white"><div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-4 px-6 py-5"><a href="/" className="font-semibold">TeleLink Health</a><AuthControls onSessionChange={setSession} /></div></header>
    <main className="mx-auto max-w-6xl px-6 py-10">
      <h1 className="text-3xl font-semibold">Clinic approval and commission</h1>
      <p className="mt-3 text-slate-600">Review clinic applications and set each clinic’s platform commission rate.</p>
      {session ? <PlatformAccess key={session.accessToken} token={session.accessToken} /> : <p className="mt-8">Sign in as a platform administrator to manage clinics.</p>}
    </main>
  </div>
}

function PlatformAccess({ token }: { token: string }) {
  const identity = useQuery({ queryKey: ['identity', token], queryFn: currentIdentity })
  if (identity.isPending) return <LoadingState message="Checking platform access..." />
  if (identity.isError) return <ErrorState message="Could not check your access. Check your session and backend connection." onRetry={() => void identity.refetch()} />
  if (!identity.data.global_roles.includes('platform_admin')) return <ErrorState message="Platform administrator access is required." />
  return <ClinicList token={token} />
}

function ClinicList({ token }: { token: string }) {
  const client = useQueryClient()
  const [status, setStatus] = useState('pending_review')
  const [saving, setSaving] = useState(false)
  const clinics = useInfiniteQuery({
    queryKey: ['platform-clinics', token, status],
    initialPageParam: null as string | null,
    queryFn: ({ pageParam, signal }) => listAdminClinics(status, pageParam, signal),
    getNextPageParam: page => page.next_cursor ?? undefined,
  })

  async function update(action: () => Promise<AdminClinic>) {
    setSaving(true)
    try {
      await action()
      await Promise.all([
        client.invalidateQueries({ queryKey: ['platform-clinics'] }),
        client.invalidateQueries({ queryKey: ['clinics'] }),
        client.invalidateQueries({ queryKey: ['public-clinic'] }),
        client.invalidateQueries({ queryKey: ['clinic-profile'] }),
        client.invalidateQueries({ queryKey: ['managed-clinics'] }),
      ])
    } finally { setSaving(false) }
  }

  return <section className="mt-8" aria-label="Platform clinics">
    <label className="grid max-w-xs gap-2 text-sm font-medium">Clinic status<select value={status} disabled={saving} onChange={event => setStatus(event.target.value)} className="rounded-md border bg-white p-2"><option value="">All statuses</option>{Object.entries(statuses).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
    {clinics.isPending ? <LoadingState message="Loading clinics..." /> : clinics.isError ? <ErrorState message="Could not load clinics. Check your platform access and backend connection." onRetry={() => void clinics.refetch()} /> : <>
      {!clinics.data.pages.some(page => page.items.length) && <p className="mt-6">No clinics with this status.</p>}
      <div className="mt-6 grid gap-6">{clinics.data.pages.flatMap(page => page.items).map(clinic => <ClinicCard key={clinic.tenant_id} clinic={clinic} disabled={saving || clinics.isFetching} update={update} />)}</div>
      {clinics.hasNextPage && <Button className="mt-6" disabled={saving || clinics.isFetching} onClick={() => void clinics.fetchNextPage()}>Load more clinics</Button>}
    </>}
  </section>
}

function ClinicCard({ clinic, disabled, update }: { clinic: AdminClinic; disabled: boolean; update: (action: () => Promise<AdminClinic>) => Promise<void> }) {
  const [reason, setReason] = useState('')
  const [commission, setCommission] = useState(String(clinic.commission_bps / 100))
  const [message, setMessage] = useState('')

  async function submit(action: () => Promise<AdminClinic>, success: string) {
    setMessage('')
    try { await update(action); setReason(''); setMessage(success) }
    catch (error) {
      if (error instanceof ApiError && [401, 403].includes(error.status)) setMessage('Your session or permissions changed. Sign in again as a platform administrator.')
      else if (error instanceof ApiError && [404, 409].includes(error.status)) setMessage('This clinic changed or is unavailable. Refresh the page before trying again.')
      else if (error instanceof ApiError && error.status === 422) setMessage('Check the review reason and commission rate, then try again.')
      else setMessage('Could not save the change. Your edits are still here; try again.')
    }
  }

  function review(decision: ReviewDecision) {
    if (decision !== 'approve' && (!reason.trim() || /[<>]/.test(reason))) { setMessage('Enter a plain-text reason for rejection or suspension.'); return }
    void submit(() => reviewClinic(clinic.tenant_id, decision, reason), 'Clinic review saved.')
  }

  return <article className="rounded-xl border bg-white p-6">
    <div className="flex flex-wrap justify-between gap-3"><h2 className="text-xl font-semibold">{clinic.name}</h2><span className="text-sm font-medium">{statuses[clinic.status]}</span></div>
    <p className="mt-2 text-sm text-slate-600">{clinic.branding.description}</p>
    <p className="mt-3 break-all text-xs text-slate-500">Clinic ID: {clinic.tenant_id}</p>
    <a href={`/clinic-admin/clinics/${clinic.tenant_id}/profile`} className="mt-3 inline-block text-sm underline">View clinic profile</a>
    {clinic.review_reason && <p className="mt-4 whitespace-pre-wrap text-sm">Review reason: {clinic.review_reason}</p>}
    <fieldset disabled={disabled} className="mt-5 grid gap-4">
      <legend className="sr-only">Review {clinic.name}</legend>
      {(clinic.status === 'pending_review' || clinic.status === 'active') && <label className="grid gap-2 text-sm">Reason for {clinic.status === 'active' ? 'suspension' : 'rejection'}<textarea value={reason} maxLength={2000} onChange={event => setReason(event.target.value)} className="rounded-md border p-2" rows={2} /></label>}
      <div className="flex flex-wrap gap-3">
        {clinic.status !== 'active' && <Button onClick={() => review('approve')}>Approve clinic</Button>}
        {clinic.status === 'pending_review' && <Button variant="outline" onClick={() => review('reject')}>Reject clinic</Button>}
        {clinic.status === 'active' && <Button variant="outline" onClick={() => review('suspend')}>Suspend clinic</Button>}
      </div>
    </fieldset>
    <form className="mt-6 border-t pt-5" onSubmit={event => {
      event.preventDefault()
      const bps = Math.round(Number(commission) * 100)
      if (!/^\d+(?:\.\d{1,2})?$/.test(commission) || bps < 0 || bps > 10000) { setMessage('Enter a commission from 0 to 100%, with at most two decimal places.'); return }
      void submit(() => saveCommission(clinic.tenant_id, bps), 'Commission saved.')
    }}>
      <fieldset disabled={disabled} className="flex flex-wrap items-end gap-4">
        <legend className="sr-only">Commission for {clinic.name}</legend>
        <label className="grid gap-2 text-sm">Commission (%)<input type="number" min="0" max="100" step="0.01" required value={commission} onChange={event => setCommission(event.target.value)} className="w-40 rounded-md border p-2" /></label>
        <Button type="submit" variant="outline">Save commission</Button>
      </fieldset>
      <p className="mt-3 text-xs text-slate-600">Current rate: {clinic.commission_bps / 100}%. Changes apply to future payments.</p>
    </form>
    <p role="status" className="mt-4 text-sm">{message}</p>
  </article>
}
