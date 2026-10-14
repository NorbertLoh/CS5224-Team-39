import { useState } from 'react'
import type { FormEvent } from 'react'
import { useInfiniteQuery, useQueryClient } from '@tanstack/react-query'
import { readSession } from '@/auth/session'
import { ApiError } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { ErrorState } from '@/components/ErrorState'
import { LoadingState } from '@/components/LoadingState'
import { assignStaff, listStaff, revokeStaff, saveStaff } from './api'
import { ClinicContext } from './ClinicContext'
import type { Membership, StaffRole } from './api'

const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

export function StaffManagement({ tenantId }: { tenantId: string | undefined }) {
  if (!tenantId || !uuid.test(tenantId)) return <ErrorState message="Clinic address is invalid." />
  if (!readSession()) return <main className="mx-auto max-w-xl px-6 py-16"><ErrorState message="Sign in as a clinic or platform administrator to manage staff." /><a href="/" className="mt-5 inline-block underline">Return home to sign in</a></main>
  return <StaffPage key={tenantId} tenantId={tenantId} />
}

function StaffPage({ tenantId }: { tenantId: string }) {
  const client = useQueryClient()
  const [email, setEmail] = useState('')
  const [role, setRole] = useState('doctor')
  const [editing, setEditing] = useState<Membership | null>(null)
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState('')
  const staff = useInfiniteQuery({
    queryKey: ['staff', readSession()?.accessToken, tenantId],
    initialPageParam: null as string | null,
    queryFn: ({ pageParam, signal }) => listStaff(tenantId, pageParam, signal),
    getNextPageParam: page => page.next_cursor ?? undefined,
  })

  function reset() { setEmail(''); setRole('doctor'); setEditing(null) }

  function edit(item: Membership) {
    setEmail('')
    setRole(item.roles.length === 2 ? 'both' : item.roles[0])
    setEditing(item)
    setMessage('')
    document.getElementById('staff-role')?.focus()
  }

  async function mutate(action: () => Promise<unknown>, success: string) {
    setSaving(true)
    setMessage('')
    try {
      await action()
      reset()
      setMessage(success)
      await Promise.all([
        client.invalidateQueries({ queryKey: ['staff'] }),
        client.invalidateQueries({ queryKey: ['identity'] }),
        client.invalidateQueries({ queryKey: ['managed-clinics'] }),
        client.invalidateQueries({ queryKey: ['clinic-doctors', tenantId] }),
      ])
    } catch (error) {
      if (error instanceof ApiError && error.status === 409) setMessage('Keep at least one active clinic administrator. Add another administrator before removing this role or access.')
      else if (error instanceof ApiError && error.status === 404) setMessage('Could not find an existing account with this email, or your clinic access has changed. Check the email and try again.')
      else if (error instanceof ApiError && [401, 403].includes(error.status)) setMessage('Your session or permissions have changed. Return home to sign in again.')
      else setMessage('Could not save the staff change. Your edits are still here; try again.')
    } finally { setSaving(false) }
  }

  function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const roles: StaffRole[] = role === 'both' ? ['doctor', 'clinic_admin'] : [role as StaffRole]
    void mutate(() => editing
      ? saveStaff(tenantId, editing.subject_id, roles)
      : assignStaff(tenantId, email, roles), 'Staff roles saved. Access is active.')
  }

  return <div className="min-h-screen bg-slate-50 text-slate-900">
    <main className="mx-auto max-w-6xl px-6 py-10">
      <a href={`/clinic-admin/clinics/${tenantId}/profile`} className="mb-5 inline-block text-sm underline">Clinic profile</a>
      <h1 className="text-3xl font-semibold">Staff management</h1>
      <ClinicContext tenantId={tenantId} />
      <p className="mt-3 text-sm text-slate-600">Assign an existing account to this clinic by email. Revoking access keeps the membership record; saving roles reactivates it.</p>
      <p role="status" className="my-5 text-sm">{message}</p>
      {staff.isPending ? <LoadingState message="Loading staff..." /> : staff.isError ? <><ErrorState message="Could not load staff. Check your administrator access and backend connection." onRetry={() => void staff.refetch()} /><a href="/" className="mt-5 inline-block underline">Return home</a></> : <>
        <form onSubmit={save} className="rounded-xl border bg-white p-6">
          <fieldset disabled={saving || staff.isFetching} className="grid gap-4 sm:grid-cols-2">
            <legend className="mb-4 text-lg font-semibold">{editing ? 'Change roles or reactivate staff' : 'Assign staff'}</legend>
            {editing ? <div className="grid gap-2 text-sm"><span>Account</span><p className="break-words font-medium">{editing.subject.display_name}{editing.subject.email && <span className="block font-normal text-slate-600">{editing.subject.email}</span>}</p></div> : <label className="grid gap-2 text-sm">Email address<input id="staff-email" type="email" autoComplete="email" value={email} required onChange={event => setEmail(event.target.value)} className="w-full rounded-md border p-2" aria-describedby="staff-email-help" /></label>}
            <label className="grid gap-2 text-sm">Roles<select id="staff-role" value={role} onChange={event => setRole(event.target.value)} className="rounded-md border p-2"><option value="doctor">Doctor</option><option value="clinic_admin">Clinic administrator</option><option value="both">Doctor and clinic administrator</option></select></label>
            <p id="staff-email-help" className="text-sm text-slate-600 sm:col-span-2">Use the email of an existing account. This page does not create accounts.</p>
            <div className="flex gap-3"><Button type="submit">{saving ? 'Saving...' : 'Save roles'}</Button>{editing && <Button type="button" variant="outline" onClick={reset}>Cancel</Button>}</div>
          </fieldset>
        </form>
        <section className="mt-8" aria-label="Clinic staff">
          <h2 className="text-xl font-semibold">Memberships</h2>
          {!staff.data.pages.some(page => page.items.length) && <p className="mt-4 text-sm text-slate-600">No staff memberships yet.</p>}
          <ul className="mt-4 grid gap-4">{staff.data.pages.flatMap(page => page.items).map(item => <li key={item.membership_id} className="flex flex-wrap items-center justify-between gap-4 rounded-xl border bg-white p-5">
            <div className="min-w-0"><p className="break-words font-medium">{item.subject.display_name}</p>{item.subject.email && <p className="mt-1 break-all text-sm text-slate-600">{item.subject.email}</p>}<p className="mt-2 text-sm">{item.roles.map(value => value === 'doctor' ? 'Doctor' : 'Clinic administrator').join(', ')} &middot; {item.status === 'active' ? 'Active' : 'Revoked'}</p></div>
            <div className="flex flex-wrap gap-3"><Button variant="outline" disabled={saving || staff.isFetching} onClick={() => edit(item)}>{item.status === 'active' ? 'Edit roles' : 'Reactivate'}</Button>{item.status === 'active' && <Button variant="outline" disabled={saving || staff.isFetching} onClick={() => {
              if (window.confirm(`Revoke clinic access for ${item.subject.display_name}${item.subject.email ? ` (${item.subject.email})` : ''}?`)) void mutate(() => revokeStaff(tenantId, item.subject_id), 'Staff access revoked.')
            }}>Revoke access</Button>}</div>
          </li>)}</ul>
          {staff.hasNextPage && <Button className="mt-5" disabled={saving || staff.isFetching} onClick={() => void staff.fetchNextPage()}>Load more staff</Button>}
        </section>
      </>}
    </main>
  </div>
}
