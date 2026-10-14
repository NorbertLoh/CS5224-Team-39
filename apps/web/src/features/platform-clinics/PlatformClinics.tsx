import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { AuthControls } from '@/auth/AuthControls'
import { readSession } from '@/auth/session'
import { ErrorState } from '@/components/ErrorState'
import { LoadingState } from '@/components/LoadingState'
import { currentIdentity } from '../clinics/api'
import { ClinicList } from './ClinicList'
import { ClinicManagement } from './ClinicManagement'

export function PlatformClinics({ tenantId }: { tenantId?: string }) {
  const [session, setSession] = useState(readSession)
  return <div className="min-h-screen bg-slate-50 text-slate-900">
    <header className="border-b bg-white"><div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-4 px-6 py-5"><a href="/" className="font-semibold">TeleLink Health</a><AuthControls onSessionChange={setSession} /></div></header>
    <main className="mx-auto max-w-6xl px-6 py-10">
      {tenantId && <a href="/platform-admin/clinics" className="mb-6 inline-block text-sm underline">Back to clinics</a>}
      <h1 className="text-3xl font-semibold">{tenantId ? 'Manage clinic' : 'Platform clinics'}</h1>
      <p className="mt-3 text-slate-600">{tenantId ? 'Review this clinic and set its platform commission rate.' : 'Select a clinic to review its application and manage commission.'}</p>
      {session ? <PlatformAccess key={session.accessToken} token={session.accessToken} tenantId={tenantId} /> : <p className="mt-8">Sign in as a platform administrator to manage clinics.</p>}
    </main>
  </div>
}
function PlatformAccess({ token, tenantId }: { token: string; tenantId?: string }) {
  const identity = useQuery({ queryKey: ['identity', token], queryFn: currentIdentity })
  if (identity.isPending) return <LoadingState message="Checking platform access..." />
  if (identity.isError) return <ErrorState message="Could not check your access. Check your session and backend connection." onRetry={() => void identity.refetch()} />
  if (!identity.data.global_roles.includes('platform_admin')) return <ErrorState message="Platform administrator access is required." />
  return tenantId ? <ClinicManagement token={token} tenantId={tenantId} /> : <ClinicList token={token} />
}
