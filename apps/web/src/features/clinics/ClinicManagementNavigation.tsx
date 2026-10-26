import { useQuery } from '@tanstack/react-query'
import { readSession } from '../../auth/session'
import { readClinic } from '../clinic-profile/logo-api'

const pages = [
  { kind: 'profile', label: 'Profile' },
  { kind: 'staff', label: 'Staff' },
  { kind: 'appointments', label: 'Appointments' },
  { kind: 'payments', label: 'Payments' },
  { kind: 'orders', label: 'Medicine & delivery' },
  { kind: 'settings', label: 'Settings' },
]

export function ClinicManagementNavigation({
  tenantId,
  active,
  hasClinicMembership,
}: {
  tenantId: string
  active: string
  hasClinicMembership: boolean
}) {
  const clinic = useQuery({
    queryKey: ['clinic-profile', readSession()?.accessToken, tenantId],
    queryFn: () => readClinic(tenantId),
  })

  return (
    <div className="border-t bg-slate-50">
      <div className="mx-auto max-w-6xl px-6 py-4">
        <div className="mb-3 flex flex-wrap items-center gap-x-5 gap-y-2">
          <p className="break-words font-semibold">
            {clinic.data?.name ??
              (clinic.isPending ? 'Loading clinic...' : 'Selected clinic')}
          </p>
          <a
            href="/clinic-admin"
            className="text-sm text-slate-600 underline underline-offset-4"
          >
            Change clinic
          </a>
        </div>
        <nav aria-label="Clinic management" className="flex flex-wrap gap-2">
          {pages
            .filter(
              (page) =>
                !['orders', 'appointments', 'settings'].includes(page.kind) ||
                hasClinicMembership,
            )
            .map((page) => (
              <a
                key={page.kind}
                href={`/clinic-admin/clinics/${tenantId}/${page.kind}`}
                aria-current={active === page.kind ? 'page' : undefined}
                className={`rounded-md px-3 py-2 text-sm font-medium focus-visible:outline-2 focus-visible:outline-offset-2 ${active === page.kind ? 'bg-slate-900 text-white' : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'}`}
              >
                {page.label}
              </a>
            ))}
        </nav>
      </div>
    </div>
  )
}
