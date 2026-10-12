import { Link, useParams } from 'react-router'

export function NotFound() {
  return <section><h1>Page not found</h1><p>This page does not exist.</p><Link to="/">Back to portals</Link></section>
}

export function RouteError() {
  return <main id="main-content" className="content"><h1>Unable to open this page</h1><p>Please try again.</p><Link to="/">Back to portals</Link></main>
}

export function ClinicStorefront() {
  const { clinicSlug } = useParams()
  return <main id="main-content" className="content"><p className="eyebrow">Clinic preview</p><h1>Care starts here.</h1><p>Clinic: {clinicSlug}</p><p>Clinic branding and booking will be added in the storefront task.</p><Link to="/patient">Explore the patient portal</Link></main>
}
