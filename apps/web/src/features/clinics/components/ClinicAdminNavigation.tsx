import type { Identity } from '@/auth/identity'
import { ClinicManagementNavigation } from '@/features/clinics/components/ClinicManagementNavigation'
import type { Route } from '@/navigation/access'
import { clinicIds } from '@/navigation/access'

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
            className={`rounded-md px-3 py-2 text-sm font-medium focus-visible:outline-2 focus-visible:outline-offset-2 ${active === page.href ? 'bg-slate-900 text-white' : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'}`}
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
