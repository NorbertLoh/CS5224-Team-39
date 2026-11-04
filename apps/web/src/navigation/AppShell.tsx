import { AuthControls } from '@/auth/AuthControls'
import { currentIdentity } from '@/auth/identity'
import type { Session } from '@/auth/session'
import { readSession } from '@/auth/session'
import { ErrorState } from '@/components/ErrorState'
import { LoadingState } from '@/components/LoadingState'
import { ClinicAdminNavigation } from '@/features/clinics/components/ClinicAdminNavigation'
import { PatientNavigation } from '@/features/patient/components/PatientNavigation'
import type { Route } from '@/navigation/access'
import { canAccess, hasRole } from '@/navigation/access'
import { DoctorNavigation } from '@/navigation/DoctorNavigation'
import { PlatformNavigation } from '@/navigation/PlatformNavigation'
import { WorkspaceSwitcher } from '@/navigation/WorkspaceSwitcher'
import { useQuery } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { useEffect, useState } from 'react'

export function AppShell({
  route,
  children,
}: {
  route: Route
  children: (session: Session | null) => ReactNode
}) {
  const [session, setSession] = useState(readSession)
  const identity = useQuery({
    queryKey: ['identity', session?.accessToken],
    queryFn: currentIdentity,
    enabled: Boolean(session),
    staleTime: 0,
    refetchOnWindowFocus: true,
    refetchInterval: 30000,
  })
  const requiresSignIn =
    ('role' in route ||
      route.kind === 'clinic-registration' ||
      route.kind === 'doctor-application') &&
    !session
  useEffect(() => {
    if (requiresSignIn) {
      if (route.kind === 'clinic-registration')
        sessionStorage.setItem('telelink.after-sign-in', '/register-clinic')
      if (route.kind === 'doctor-application')
        sessionStorage.setItem('telelink.after-sign-in', '/join-as-doctor')
      window.location.replace('/sign-in')
    }
  }, [requiresSignIn, route.kind])

  if (requiresSignIn)
    return <LoadingState message="Redirecting to sign in..." />
  if (route.kind === 'sign-in')
    return <AuthControls presentation="page" onSessionChange={setSession} />
  let content = children(session)
  if ('role' in route) {
    if (identity.isPending)
      content = <LoadingState message="Checking your access..." />
    else if (identity.isError)
      content = (
        <ErrorState
          message="Could not verify your access. Check your session and connection."
          onRetry={() => void identity.refetch()}
        />
      )
    else if (!canAccess(identity.data, route))
      content = (
        <ErrorState message="You do not have access to this role or clinic. Use the workspace switcher above to return to a workspace you can access." />
      )
  }
  return (
    <>
      <header className="border-b bg-white">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-4 px-4 py-4 sm:px-6">
          <a href="/" className="text-xl font-semibold">
            TeleLink Health
          </a>
          <div className="flex flex-wrap items-center gap-3">
            {session && identity.isSuccess && (
              <WorkspaceSwitcher identity={identity.data} route={route} />
            )}
            <AuthControls onSessionChange={setSession} compact />
          </div>
        </div>
        {session &&
          identity.isSuccess &&
          hasRole(identity.data, 'patient') &&
          (('role' in route &&
            route.role === 'patient' &&
            canAccess(identity.data, route)) ||
            route.kind === 'home' ||
            route.kind === 'storefront') && (
            <PatientNavigation route={route} identity={identity.data} />
          )}
        {session && !('role' in route) && identity.isPending && (
          <LoadingState message="Loading your workspaces..." />
        )}
        {session &&
          identity.isSuccess &&
          (route.kind === 'doctor-application' ||
            ('role' in route &&
              route.role === 'doctor' &&
              canAccess(identity.data, route))) && (
            <DoctorNavigation route={route} identity={identity.data} />
          )}
        {session &&
          identity.isSuccess &&
          'role' in route &&
          route.role === 'clinic_admin' &&
          canAccess(identity.data, route) && (
            <ClinicAdminNavigation route={route} identity={identity.data} />
          )}
        {session && !('role' in route) && identity.isError && (
          <ErrorState
            message="Could not load your workspaces. Check your session and connection."
            onRetry={() => void identity.refetch()}
          />
        )}
        {session &&
          identity.isSuccess &&
          'role' in route &&
          route.role === 'platform_admin' &&
          canAccess(identity.data, route) && (
            <PlatformNavigation route={route} />
          )}
      </header>
      {content}
    </>
  )
}
