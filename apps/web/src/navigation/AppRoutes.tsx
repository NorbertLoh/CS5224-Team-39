import { HomePage } from '../features/clinics/HomePage'
import { ClinicStorefront } from '../features/storefront/ClinicStorefront'
import { ClinicProfileEditor } from '../features/clinic-profile/ClinicProfileEditor'
import { StaffManagement } from '../features/staff/StaffManagement'
import { PlatformClinics } from '../features/platform-clinics/PlatformClinics'
import { ManagedClinics } from '../features/clinics/ManagedClinics'
import { ClinicDirectory } from '../features/clinics/ClinicDirectory'
import { ErrorState } from '../components/ErrorState'
import { roleLabels } from './access'
import type { Route } from './access'
import type { Session } from '../auth/session'

export function AppRoutes({ route, session }: { route: Route; session: Session | null }) {
  switch (route.kind) {
    case 'home': return <HomePage />
    case 'storefront': return <ClinicStorefront slug={route.slug} />
    case 'profile': return <ClinicProfileEditor tenantId={route.tenantId} />
    case 'staff': return <StaffManagement tenantId={route.tenantId} />
    case 'platform': return session && <PlatformClinics token={session.accessToken} tenantId={route.tenantId} />
    case 'role': return <main className="mx-auto max-w-6xl px-6 py-10">
      <h1 className="text-3xl font-semibold">{roleLabels[route.role]}</h1>
      {route.role === 'patient' && <section className="mt-8"><h2 className="text-xl font-semibold">Explore clinics</h2><ClinicDirectory /></section>}
      {route.role === 'clinic_admin' && session && <ManagedClinics session={session} />}
      {route.role === 'doctor' && <p className="mt-5">{route.tenantId ? `Selected clinic: ${route.tenantId}. Doctor availability and consultation pages are coming soon.` : 'Choose a clinic above to enter your doctor workspace.'}</p>}
    </main>
    case 'missing': return <ErrorState message="Page not found." />
  }
}
