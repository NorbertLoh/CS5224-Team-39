import type { Route } from '@/navigation/access'

export function DoctorNavigation({ route }: { route: Route }) {
  const tenantId = 'tenantId' in route ? route.tenantId : undefined
  const base = tenantId ? `/doctor/clinics/${tenantId}` : '/doctor'
  const availability = route.kind === 'doctor-availability'
  const pages = [
    { href: base, label: 'Appointments', active: !availability },
    {
      href: `${base}/availability`,
      label: 'Availability',
      active: availability,
    },
  ]

  return (
    <nav
      aria-label="Doctor workspace"
      className="mx-auto flex max-w-6xl flex-wrap gap-2 px-6 pb-4"
    >
      {pages.map((page) => (
        <a
          key={page.href}
          href={page.href}
          aria-current={page.active ? 'page' : undefined}
          className={`rounded-md px-3 py-2 text-sm font-medium focus-visible:outline-2 focus-visible:outline-offset-2 ${page.active ? 'bg-slate-900 text-white' : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'}`}
        >
          {page.label}
        </a>
      ))}
    </nav>
  )
}
