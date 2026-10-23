import type { Identity } from '../features/clinics/api'

export type Role = 'patient' | 'doctor' | 'clinic_admin' | 'platform_admin'
export type Route =
  | { kind: 'home' }
  | { kind: 'sign-in' }
  | { kind: 'storefront'; slug: string }
  | { kind: 'booking'; role: 'patient'; slug: string }
  | { kind: 'checkout'; role: 'patient' }
  | { kind: 'medication-orders'; role: 'patient' }
  | { kind: 'prescriptions' | 'documents'; role: 'patient' }
  | { kind: 'role'; role: Role; tenantId?: string }
  | { kind: 'clinic-appointments'; role: 'clinic_admin' }
  | { kind: 'consultation'; role: 'patient' | 'doctor' }
  | {
      kind: 'profile' | 'staff' | 'payments' | 'orders'
      role: 'clinic_admin'
      tenantId: string
    }
  | { kind: 'platform'; role: 'platform_admin'; tenantId?: string }
  | { kind: 'missing' }

export const roleLabels: Record<Role, string> = {
  patient: 'Patient',
  doctor: 'Doctor',
  clinic_admin: 'Clinic administration',
  platform_admin: 'Platform administration',
}
export const rolePaths: Record<Role, string> = {
  patient: '/patient',
  doctor: '/doctor',
  clinic_admin: '/clinic-admin',
  platform_admin: '/platform-admin/clinics',
}
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

export function clinicIds(identity: Identity, role: 'doctor' | 'clinic_admin') {
  return [
    ...new Set(
      identity.memberships
        .filter((item) => item.status === 'active' && item.roles.includes(role))
        .map((item) => item.tenant_id),
    ),
  ]
}

export function hasRole(identity: Identity, role: Role) {
  if (role === 'doctor' || role === 'clinic_admin')
    return clinicIds(identity, role).length > 0
  return identity.global_roles.includes(role)
}

export function canAccess(identity: Identity, route: Route) {
  if (!('role' in route)) return true
  // Medicine readiness requires active owning-clinic administration (D03).
  if (route.kind === 'orders')
    return clinicIds(identity, 'clinic_admin').includes(route.tenantId)
  // Tenant APIs explicitly permit platform administrators to manage clinics.
  if (
    route.role === 'clinic_admin' &&
    identity.global_roles.includes('platform_admin')
  )
    return true
  if (!hasRole(identity, route.role)) return false
  if (
    (route.role === 'doctor' || route.role === 'clinic_admin') &&
    'tenantId' in route &&
    route.tenantId
  ) {
    return clinicIds(identity, route.role).includes(route.tenantId)
  }
  return true
}

export function parseRoute(path: string): Route {
  const normalized = path.replace(/\/$/, '') || '/'
  if (normalized === '/sign-in') return { kind: 'sign-in' }
  if (normalized === '/' || normalized === '/auth/callback')
    return { kind: 'home' }
  if (
    normalized === '/patient/checkout' ||
    normalized === '/payments/return' ||
    normalized === '/appointments'
  )
    return { kind: 'checkout', role: 'patient' }
  if (normalized === '/patient') return { kind: 'role', role: 'patient' }
  if (normalized === '/patient/prescriptions')
    return { kind: 'prescriptions', role: 'patient' }
  if (normalized === '/patient/documents')
    return { kind: 'documents', role: 'patient' }
  if (normalized === '/patient/medication-orders')
    return { kind: 'medication-orders', role: 'patient' }
  if (normalized === '/doctor') return { kind: 'role', role: 'doctor' }
  if (normalized === '/patient/consultation')
    return { kind: 'consultation', role: 'patient' }
  if (normalized === '/doctor/consultation')
    return { kind: 'consultation', role: 'doctor' }
  if (normalized === '/clinic-admin')
    return { kind: 'role', role: 'clinic_admin' }
  if (normalized === '/clinic-admin/appointments')
    return { kind: 'clinic-appointments', role: 'clinic_admin' }
  const booking = /^\/patient\/clinics\/([^/]+)\/book$/.exec(normalized)
  if (booking) return { kind: 'booking', role: 'patient', slug: booking[1] }
  if (
    normalized === '/platform-admin' ||
    normalized === '/platform-admin/clinics'
  )
    return { kind: 'platform', role: 'platform_admin' }
  const storefront = /^\/clinics\/([^/]+)$/.exec(normalized)
  if (storefront) return { kind: 'storefront', slug: storefront[1] }
  const platform = /^\/platform-admin\/clinics\/([^/]+)$/.exec(normalized)
  if (platform && uuid.test(platform[1]))
    return {
      kind: 'platform',
      role: 'platform_admin',
      tenantId: platform[1].toLowerCase(),
    }
  const clinic =
    /^\/clinic-admin\/clinics\/([^/]+)\/(profile|staff|payments|orders)$/.exec(
      normalized,
    )
  if (clinic && uuid.test(clinic[1]))
    return {
      kind: clinic[2] as 'profile' | 'staff' | 'payments' | 'orders',
      role: 'clinic_admin',
      tenantId: clinic[1].toLowerCase(),
    }
  const doctor = /^\/doctor\/clinics\/([^/]+)$/.exec(normalized)
  if (doctor && uuid.test(doctor[1]))
    return { kind: 'role', role: 'doctor', tenantId: doctor[1].toLowerCase() }
  return { kind: 'missing' }
}
