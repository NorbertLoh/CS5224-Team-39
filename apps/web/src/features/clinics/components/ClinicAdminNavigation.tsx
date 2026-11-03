import type { Identity } from '@/auth/identity'
import { ClinicManagementNavigation } from '@/features/clinics/components/ClinicManagementNavigation'
import type { Route } from '@/navigation/access'
import { clinicIds } from '@/navigation/access'
import { tabClassName } from '@/lib/tab-styles'

const pages = [
  { href: '/clinic-admin', label: 'Manage clinic' },
  { href: '/clinic-admin/appointments', label: 'Appointments' },
]

export function ClinicAdminNavigation({
  route,
  identity,
}: {
  route: Route
  identity: Identity
}) {
  const tenantId = 'tenantId' in route ? route.tenantId : undefined
  const managementHref = tenantId
    ? `/clinic-admin/clinics/${tenantId}/profile`
    : '/clinic-admin'
  const active =
    route.kind === 'clinic-appointments' && !tenantId
      ? '/clinic-admin/appointments'
      : '/clinic-admin'

  return (
    <>
      <nav
        aria-label="Clinic administration workspace"
        className="mx-auto flex max-w-6xl flex-wrap gap-2 px-6 pb-4"
      >
        {pages.map((page) => (
          <a
            key={page.href}
            href={page.href === '/clinic-admin' ? managementHref : page.href}
            aria-current={active === page.href ? 'page' : undefined}
            className={tabClassName(active === page.href)}
          >
            {page.label}
          </a>
        ))}
      </nav>
      {tenantId && (
        <ClinicManagementNavigation
          tenantId={tenantId}
          active={
            route.kind === 'clinic-appointments' ? 'appointments' : route.kind
          }
          hasClinicMembership={clinicIds(identity, 'clinic_admin').includes(
            tenantId,
          )}
        />
      )}
    </>
  )
}
