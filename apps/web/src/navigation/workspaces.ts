import type { Identity } from '@/auth/identity'
import {
  clinicIds,
  hasRole,
  rolePaths,
  type Role,
  type Route,
} from '@/navigation/access'

export const workspaceLabels: Record<Role, string> = {
  patient: 'Patient',
  doctor: 'Doctor',
  clinic_admin: 'Clinic admin',
  platform_admin: 'Platform admin',
}

export function availableWorkspaces(identity: Identity) {
  return (
    ['patient', 'doctor', 'clinic_admin', 'platform_admin'] as const
  ).filter((role) => hasRole(identity, role))
}

export function currentWorkspace(
  identity: Identity,
  route: Route,
): Role | 'registration' | undefined {
  if (route.kind === 'doctor-application')
    return hasRole(identity, 'doctor') ? 'doctor' : 'registration'
  if (route.kind === 'clinic-registration') return undefined
  if ('role' in route) {
    if (hasRole(identity, route.role)) return route.role
    // Platform administrators may manage clinic profile/staff/payments without membership.
    if (route.role === 'clinic_admin' && hasRole(identity, 'platform_admin'))
      return 'platform_admin'
    return undefined
  }
  if (
    (route.kind === 'home' || route.kind === 'storefront') &&
    hasRole(identity, 'patient')
  )
    return 'patient'
  return undefined
}

/** Carry URL clinic context only when the destination role has current access. */
export function workspaceHref(
  identity: Identity,
  role: Role,
  route: Route,
  applicationClinic?: string | null,
) {
  const requested =
    'tenantId' in route
      ? route.tenantId
      : route.kind === 'doctor-application'
        ? applicationClinic
        : undefined
  if (
    requested &&
    (role === 'doctor' || role === 'clinic_admin') &&
    clinicIds(identity, role).includes(requested)
  )
    return role === 'doctor'
      ? `/doctor/clinics/${requested}`
      : `/clinic-admin/clinics/${requested}/profile`
  return rolePaths[role]
}
