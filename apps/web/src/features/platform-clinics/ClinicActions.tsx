import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { ApiError } from '@/lib/api'
import { reviewClinic, saveCommission, clinicStatuses } from './api'
import type { AdminClinic, ReviewDecision } from './api'

export function ClinicActions({ clinic, disabled, update }: { clinic: AdminClinic; disabled: boolean; update: (action: () => Promise<AdminClinic>) => Promise<void> }) {
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
    <div className="flex flex-wrap justify-between gap-3"><h2 className="text-xl font-semibold">{clinic.name}</h2><span className="text-sm font-medium">{clinicStatuses[clinic.status]}</span></div>
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
