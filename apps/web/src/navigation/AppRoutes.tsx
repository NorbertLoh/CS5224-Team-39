import type { Session } from '@/auth/session'
import { ErrorState } from '@/components/ErrorState'
import { AppointmentSchedule } from '@/features/appointments/AppointmentSchedule'
import { AvailabilityEditor } from '@/features/availability/AvailabilityEditor'
import { ClinicBooking } from '@/features/booking/ClinicBooking'
import { LiveCheckoutPage } from '@/features/checkout/LiveCheckoutPage'
import { ClinicProfileEditor } from '@/features/clinic-profile/ClinicProfileEditor'
import {
  ClinicRegistration,
  ClinicSettings,
  HomePage,
  ManagedClinics,
} from '@/features/clinics'
import { LiveOrders } from '@/features/fulfilment'
import { PatientProfilePage, PatientRecordsPage } from '@/features/patient'
import { ClinicPayments } from '@/features/payments/ClinicPayments'
import { PlatformClinics } from '@/features/platform-clinics/PlatformClinics'
import { StaffManagement } from '@/features/staff/StaffManagement'
import { ClinicStorefront } from '@/features/storefront/ClinicStorefront'
import { BookedConsultation } from '@/features/video'
import type { Route } from '@/navigation/access'
import { roleLabels } from '@/navigation/access'
import { WorkspacePage } from '@/navigation/WorkspacePage'

export function AppRoutes({
  route,
  session,
}: {
  route: Route
  session: Session | null
}) {
  switch (route.kind) {
    case 'clinic-registration':
      return <ClinicRegistration />
    case 'doctor-availability':
      return (
        <WorkspacePage title="Doctor availability">
          <AvailabilityEditor key={route.tenantId} tenantId={route.tenantId} />
        </WorkspacePage>
      )
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
    case 'patient-profile':
      return <PatientProfilePage />
    case 'prescriptions':
    case 'documents':
      return <PatientRecordsPage page={route.kind} />
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
    case 'settings':
      return <ClinicSettings key={route.tenantId} tenantId={route.tenantId} />
    case 'staff':
      return <StaffManagement tenantId={route.tenantId} />
    case 'payments':
      return <ClinicPayments key={route.tenantId} tenantId={route.tenantId} />
    case 'clinic-appointments':
      return (
        <WorkspacePage title="Clinic appointments">
          <AppointmentSchedule
            key={route.tenantId}
            role="clinic_admin"
            tenantId={route.tenantId}
          />
        </WorkspacePage>
      )
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
        <WorkspacePage title={roleLabels[route.role]}>
          {route.role === 'clinic_admin' && session && (
            <ManagedClinics session={session} />
          )}
          {(route.role === 'patient' || route.role === 'doctor') && (
            <AppointmentSchedule
              key={`${route.role}:${route.tenantId ?? ''}`}
              role={route.role}
              tenantId={route.tenantId}
            />
          )}
        </WorkspacePage>
      )
    case 'missing':
      return <ErrorState message="Page not found." />
  }
}
