import { HomePage } from './features/clinics/HomePage'
import { ClinicStorefront } from './features/storefront/ClinicStorefront'
import { ClinicProfileEditor } from './features/clinic-profile/ClinicProfileEditor'
import { StaffManagement } from './features/staff/StaffManagement'
import { PlatformClinics } from './features/platform-clinics/PlatformClinics'

export default function App() {
  const path = window.location.pathname
  if (/^\/platform-admin\/clinics\/?$/.test(path)) return <PlatformClinics />
  const platformClinic = /^\/platform-admin\/clinics\/([^/]+)\/?$/.exec(path)
  if (platformClinic) return <PlatformClinics tenantId={platformClinic[1]} />
  if (path.startsWith('/clinic-admin/')) {
    const staff = /^\/clinic-admin\/clinics\/([^/]+)\/staff\/?$/.exec(path)
    if (staff) return <StaffManagement tenantId={staff[1]} />
    const route = /^\/clinic-admin\/clinics\/([^/]+)\/profile\/?$/.exec(path)
    return <ClinicProfileEditor tenantId={route?.[1]} />
  }
  if (path.startsWith('/clinics/')) {
    const route = /^\/clinics\/([^/]+)\/?$/.exec(path)
    return <ClinicStorefront slug={route?.[1]} />
  }
  return <HomePage />
}
