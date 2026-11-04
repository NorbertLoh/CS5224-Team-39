import type { Identity } from '@/auth/identity'
import { useClinicNames } from '@/features/clinics/hooks/useClinicNames'
import { useClinicMedicineAttention } from '@/features/fulfilment/pricing/clinicMedicineQueries'
import type { Route } from '@/navigation/access'
import { clinicIds } from '@/navigation/access'
import { WorkspaceNavigation } from '@/navigation/WorkspaceNavigation'
import { Building2 } from 'lucide-react'

const sections = [
  { kind: 'profile', label: 'Clinic profile' },
  { kind: 'staff', label: 'Staff' },
  { kind: 'appointments', label: 'Appointments' },
  { kind: 'payments', label: 'Payments' },
  { kind: 'medicine-pricing', label: 'Medicine Pricing' },
  { kind: 'orders', label: 'Medicine Delivery' },
  { kind: 'settings', label: 'Settings' },
]

export function ClinicAdminNavigation({
  route,
  identity,
}: {
  route: Route
  identity: Identity
}) {
  const tenantId = 'tenantId' in route ? route.tenantId : undefined
  const clinics = clinicIds(identity, 'clinic_admin')
  const hasMembership = Boolean(tenantId && clinics.includes(tenantId))
  const attention = useClinicMedicineAttention(hasMembership ? tenantId ?? '' : '')
  // Platform administrators can view selected management pages without membership.
  const visibleClinics = tenantId && !hasMembership ? [tenantId] : clinics
  const clinicName = useClinicNames(visibleClinics, true)
  const active =
    route.kind === 'clinic-appointments' ? 'appointments' : route.kind
  const scoped = Boolean(tenantId)
  const links = tenantId
    ? sections
        .filter(
          (page) =>
            hasMembership ||
            !['appointments', 'medicine-pricing', 'orders', 'settings'].includes(page.kind),
        )
        .map((page) => ({
          href: `/clinic-admin/clinics/${tenantId}/${page.kind}`,
          label: page.label,
          active: active === page.kind,
          attention:
            page.kind === 'medicine-pricing'
              ? attention.pricing
              : page.kind === 'orders'
                ? attention.delivery
                : undefined,
        }))
    : [
        {
          href: '/clinic-admin',
          label: 'My clinics',
          active: route.kind === 'role',
        },
        {
          href: '/clinic-admin/appointments',
          label: 'Appointments',
          active: route.kind === 'clinic-appointments',
        },
      ].filter((page) => clinics.length > 0 || page.href === '/clinic-admin')
  return (
    <WorkspaceNavigation
      title={scoped ? 'Clinic management' : 'Clinic admin workspace'}
      description={
        tenantId
          ? clinicName(tenantId) === tenantId
            ? 'Manage the selected clinic'
            : clinicName(tenantId)
          : 'Choose a clinic or view appointments across your clinics'
      }
      icon={Building2}
      links={links}
    >
      {scoped && hasMembership && (
        <label className="flex min-w-0 max-w-full items-center gap-2 text-xs font-medium text-slate-500">
          <span>Clinic</span>
          <select
            aria-label="Administration clinic"
            value={tenantId}
            className="min-h-10 min-w-0 max-w-64 rounded-lg border border-slate-200 bg-white px-3 text-sm text-slate-800 focus-visible:outline-2 focus-visible:outline-teal-600"
            onChange={(event) => {
              const clinic = event.target.value
              window.location.assign(
                clinic
                  ? `/clinic-admin/clinics/${clinic}/${sections.some((page) => page.kind === active) ? active : 'profile'}`
                  : '/clinic-admin',
              )
            }}
          >
            <option value="">All my clinics</option>
            {clinics.map((id, index) => (
              <option key={id} value={id}>
                {clinicName(id) === id ? `Clinic ${index + 1}` : clinicName(id)}
              </option>
            ))}
          </select>
        </label>
      )}
      {scoped && !hasMembership && (
        <a
          href="/platform-admin/clinics"
          className="text-sm font-medium text-teal-800 underline underline-offset-4"
        >
          Back to platform clinics
        </a>
      )}
      {!scoped && (
        <a
          href="/register-clinic"
          className="text-sm font-medium text-teal-800 underline underline-offset-4"
        >
          Register a clinic
        </a>
      )}
    </WorkspaceNavigation>
  )
}
