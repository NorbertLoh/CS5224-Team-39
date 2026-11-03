import type { Identity } from '@/auth/identity'
import type { Route } from '@/navigation/access'
import { clinicIds } from '@/navigation/access'

export function isDoctorRoute(route: Route) {
  return (
    route.kind === 'doctor-application' ||
    ('role' in route && route.role === 'doctor')
  )
}

export function doctorNavigationState(
  identity: Identity,
  route: Route,
  applicationClinic?: string | null,
) {
  const clinics = clinicIds(identity, 'doctor')
  const section =
    route.kind === 'doctor-application'
      ? 'verification'
      : route.kind === 'doctor-availability'
        ? 'availability'
        : route.kind === 'consultation'
          ? 'consultation'
          : 'appointments'
  const requested =
    'tenantId' in route
      ? route.tenantId
      : section === 'verification'
        ? applicationClinic
        : undefined
  const clinicId =
    requested && clinics.includes(requested)
      ? requested
      : section === 'availability'
        ? clinics[0]
        : undefined
  const base = clinicId ? `/doctor/clinics/${clinicId}` : '/doctor'
  const verification = clinicId
    ? `/join-as-doctor?clinic=${encodeURIComponent(clinicId)}`
    : '/join-as-doctor'
  return {
    clinics,
    clinicId,
    base,
    verification,
    section,
    canPractise: clinics.length > 0,
  }
}
