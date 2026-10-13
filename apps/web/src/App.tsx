import { HomePage } from './features/clinics/HomePage'
import { ClinicStorefront } from './features/storefront/ClinicStorefront'
import { ClinicProfileEditor } from './features/clinic-profile/ClinicProfileEditor'

export default function App() {
  const path = window.location.pathname
  if (path.startsWith('/clinic-admin/')) {
    const route = /^\/clinic-admin\/clinics\/([^/]+)\/profile\/?$/.exec(path)
    return <ClinicProfileEditor tenantId={route?.[1]} />
  }
  if (path.startsWith('/clinics/')) {
    const route = /^\/clinics\/([^/]+)\/?$/.exec(path)
    return <ClinicStorefront slug={route?.[1]} />
  }
  return <HomePage />
}
