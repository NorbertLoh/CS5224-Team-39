import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { AuthControls } from '../auth/AuthControls'
import { readSession } from '../auth/session'
import { currentIdentity } from '../features/clinics/api'
import { ErrorState } from '../components/ErrorState'
import { LoadingState } from '../components/LoadingState'
import { RoleNavigation } from './RoleNavigation'
import { canAccess } from './access'
import type { Route } from './access'
import type { ReactNode } from 'react'
import type { Session } from '../auth/session'

export function AppShell({ route, children }: { route: Route; children: (session: Session | null) => ReactNode }) {
  const [session, setSession] = useState(readSession)
  const identity = useQuery({
    queryKey: ['identity', session?.accessToken], queryFn: currentIdentity,
    enabled: Boolean(session), staleTime: 0, refetchOnWindowFocus: true, refetchInterval: 30000,
  })
  if (route.kind === 'sign-in') return <AuthControls presentation="page" onSessionChange={setSession} />
  let content = children(session)
  if ('role' in route) {
    if (!session) content = <p role="status" className="p-6">Sign in to access this page.</p>
    else if (identity.isPending) content = <LoadingState message="Checking your access..." />
    else if (identity.isError) content = <ErrorState message="Could not verify your access. Check your session and connection." onRetry={() => void identity.refetch()} />
    else if (!canAccess(identity.data, route)) content = <ErrorState message="You do not have access to this role or clinic. Choose an available role above to return to its workspace." />
  }
  return <>
    <header className="border-b bg-white">
      <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-4 px-6 py-5"><a href="/" className="text-xl font-semibold">TeleLink Health</a><AuthControls onSessionChange={setSession} /></div>
      {session && identity.isSuccess && <RoleNavigation identity={identity.data} route={route} />}
      {session && !('role' in route) && identity.isPending && <LoadingState message="Loading your roles..." />}
      {session && !('role' in route) && identity.isError && <ErrorState message="Could not load your roles. Check your session and connection." onRetry={() => void identity.refetch()} />}
    </header>
    {content}
  </>
}
