import { HomePage } from '../features/clinics/HomePage'
import { ClinicBooking } from '../features/booking/ClinicBooking'
import { AvailabilityEditor } from '../features/availability/AvailabilityEditor'
import { AppointmentSchedule } from '../features/appointments/AppointmentSchedule'
import { ClinicStorefront } from '../features/storefront/ClinicStorefront'
import { ClinicProfileEditor } from '../features/clinic-profile/ClinicProfileEditor'
import { StaffManagement } from '../features/staff/StaffManagement'
import { PlatformClinics } from '../features/platform-clinics/PlatformClinics'
import { ManagedClinics } from '../features/clinics/ManagedClinics'
import { ErrorState } from '../components/ErrorState'
import { PatientPrescriptions } from '../features/records/PatientPrescriptions'
import { DocumentList } from '../features/documents/DocumentList'
import { BookedConsultation } from '../features/video/BookedConsultation'
import { LiveCheckoutPage } from '../features/checkout/LiveCheckoutPage'
import { LiveOrders } from '../features/fulfilment/LiveOrders'
import { ClinicPayments } from '../features/payments/ClinicPayments'
import { roleLabels } from './access'
import type { Route } from './access'
import type { Session } from '../auth/session'

export function AppRoutes({
  route,
  session,
}: {
  route: Route
  session: Session | null
}) {
  switch (route.kind) {
    case 'home':
      return <HomePage />
    case 'storefront':
      return <ClinicStorefront slug={route.slug} />
    case 'booking':
      return <ClinicBooking slug={route.slug} />
    case 'checkout':
      return <LiveCheckoutPage />
    case 'medication-orders':
      return <LiveOrders role="patient" />
    case 'orders':
      return (
        <LiveOrders
          key={route.tenantId}
          role="clinic_admin"
          tenantId={route.tenantId}
        />
      )
    case 'consultation':
      return <BookedConsultation role={route.role} />
    case 'profile':
      return <ClinicProfileEditor tenantId={route.tenantId} />
    case 'staff':
      return <StaffManagement tenantId={route.tenantId} />
    case 'payments':
      return <ClinicPayments key={route.tenantId} tenantId={route.tenantId} />
    case 'platform':
      return (
        session && (
          <PlatformClinics
            token={session.accessToken}
            tenantId={route.tenantId}
          />
        )
      )
    case 'role':
      return (
        <main className="mx-auto max-w-6xl px-6 py-10">
          <h1 className="text-3xl font-semibold">{roleLabels[route.role]}</h1>
          {route.role === 'patient' && <PatientPrescriptions />}
          {route.role === 'patient' && (
            <p className="mt-6 text-sm">
              <a className="underline" href="/patient/medication-orders">
                Medication orders and delivery
              </a>
            </p>
          )}
          {route.role === 'patient' && <DocumentList role="patient" />}
          {route.role === 'clinic_admin' && session && (
            <ManagedClinics session={session} />
          )}
          {route.role === 'doctor' && (
            <AvailabilityEditor
              key={route.tenantId}
              tenantId={route.tenantId}
            />
          )}
          {route.role === 'doctor' && (
            <section className="mt-8 rounded-xl border bg-slate-50 p-6">
              <h2 className="text-xl font-semibold">Video consultation</h2>
              <p className="mt-2 text-sm text-slate-600">
                Open a booked appointment to join its video consultation.
              </p>
              <a
                className="mt-4 inline-block rounded-lg bg-slate-900 px-4 py-2 text-sm text-white"
                href={`/${route.role}/consultation`}
              >
                Choose a consultation
              </a>
            </section>
          )}
          {(route.role === 'patient' ||
            route.role === 'doctor' ||
            route.role === 'clinic_admin') && (
            <AppointmentSchedule
              key={`${route.role}:${route.tenantId ?? ''}`}
              role={route.role}
              tenantId={route.tenantId}
            />
          )}
        </main>
      )
    case 'missing':
      return <ErrorState message="Page not found." />
  }
}
