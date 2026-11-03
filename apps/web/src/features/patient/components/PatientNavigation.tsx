import type { Route } from '@/navigation/access'
import { tabClassName } from '@/lib/tab-styles'

const pages = [
  { href: '/#clinics', label: 'Find a clinic' },
  { href: '/patient', label: 'Appointments' },
  { href: '/patient/prescriptions', label: 'Prescriptions' },
  { href: '/patient/medication-orders', label: 'Orders & delivery' },
  { href: '/patient/documents', label: 'Documents' },
  { href: '/patient/profile', label: 'Profile' },
]

export function PatientNavigation({ route }: { route: Route }) {
  const active =
    route.kind === 'patient-profile'
      ? '/patient/profile'
      : route.kind === 'home' ||
          route.kind === 'storefront' ||
          route.kind === 'booking'
        ? '/#clinics'
        : route.kind === 'prescriptions'
          ? '/patient/prescriptions'
          : route.kind === 'documents'
            ? '/patient/documents'
            : route.kind === 'medication-orders'
              ? '/patient/medication-orders'
              : route.kind === 'role' ||
                  route.kind === 'checkout' ||
                  route.kind === 'consultation'
                ? '/patient'
                : undefined

  return (
    <nav
      aria-label="Patient workspace"
      className="mx-auto flex max-w-6xl flex-wrap gap-2 px-6 pb-4"
    >
      {pages.map((page) => (
        <a
          key={page.href}
          href={page.href}
          aria-current={active === page.href ? 'page' : undefined}
          className={tabClassName(active === page.href)}
        >
          {page.label}
        </a>
      ))}
    </nav>
  )
}
