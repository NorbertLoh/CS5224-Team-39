import type { Route } from '@/navigation/access'
import { WorkspaceNavigation } from '@/navigation/WorkspaceNavigation'
import { ShieldCheck } from 'lucide-react'

export function PlatformNavigation({ route }: { route: Route }) {
  return (
    <WorkspaceNavigation
      title="Platform admin workspace"
      description="Review clinics and verify doctor applications"
      icon={ShieldCheck}
      links={[
        {
          href: '/platform-admin/clinics',
          label: 'Clinics',
          active: route.kind === 'platform',
        },
        {
          href: '/platform-admin/doctors',
          label: 'Doctor applications',
          active: route.kind === 'doctor-applications-review',
        },
      ]}
    />
  )
}
