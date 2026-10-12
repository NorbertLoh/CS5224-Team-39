import { createBrowserRouter } from 'react-router'
import type { RouteObject } from 'react-router'
import App from '../App'
import { pagesFor } from '../features/registry'
import { PortalLayout, PortalOverview, RootLayout } from './layouts'
import { ClinicStorefront, NotFound, RouteError } from './pages'
import { portals } from './portals'
import type { PortalRole } from './portals'

const portalRoutes: RouteObject[] = (Object.keys(portals) as PortalRole[]).map(role => ({
  path: role,
  element: <PortalLayout role={role} />,
  children: [
    { index: true, element: <PortalOverview role={role} /> },
    ...pagesFor(role).map(page => ({ path: page.path, element: page.element })),
    { path: '*', element: <NotFound /> },
  ],
}))

export const router = createBrowserRouter([{
  path: '/',
  element: <RootLayout />,
  errorElement: <RouteError />,
  children: [
    { index: true, element: <App /> },
    { path: 'clinics/:clinicSlug', element: <ClinicStorefront /> },
    ...portalRoutes,
    { path: '*', element: <main id="main-content" className="px-5 py-12 sm:px-8"><NotFound /></main> },
  ],
}])
