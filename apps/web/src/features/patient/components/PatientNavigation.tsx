import type { Route } from '@/navigation/access'
import { WorkspaceNavigation } from '@/navigation/WorkspaceNavigation'
import { UserRound } from 'lucide-react'

const pages = [
  {
    href: '/#clinics',
    label: 'Find a clinic',
    kinds: ['home', 'storefront', 'booking'],
  },
  { href: '/patient', label: 'Appointments', kinds: ['role', 'checkout'] },
  {
    href: '/patient/prescriptions',
    label: 'Prescriptions',
    kinds: ['prescriptions'],
  },
  {
    href: '/patient/medication-orders',
    label: 'Orders & delivery',
    kinds: ['medication-orders'],
  },
  { href: '/patient/documents', label: 'Documents', kinds: ['documents'] },
  { href: '/patient/profile', label: 'My profile', kinds: ['patient-profile'] },
]

export function PatientNavigation({ route }: { route: Route }) {
  return (
    <WorkspaceNavigation
      title="Patient workspace"
      description={
        route.kind === 'consultation'
          ? 'Consultation'
          : 'Your care, appointments and health records'
      }
      icon={UserRound}
      links={pages.map(({ href, label, kinds }) => ({
        href,
        label,
        active: kinds.includes(route.kind),
      }))}
    />
  )
}
