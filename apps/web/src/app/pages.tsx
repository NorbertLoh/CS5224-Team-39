import { Link, useParams } from 'react-router'
import { Button } from '@/components/ui/button'

export function NotFound() {
  return (
    <section className="space-y-4">
      <h1 className="text-3xl font-semibold tracking-tight">Page not found</h1>
      <p className="text-muted-foreground">This page does not exist.</p>
      <Button asChild variant="outline"><Link to="/">Back to portals</Link></Button>
    </section>
  )
}

export function RouteError() {
  return (
    <main id="main-content" className="space-y-4 px-5 py-12 sm:px-8">
      <h1 className="text-3xl font-semibold tracking-tight">Unable to open this page</h1>
      <p className="text-muted-foreground">Please try again.</p>
      <Button asChild variant="outline"><Link to="/">Back to portals</Link></Button>
    </main>
  )
}

export function ClinicStorefront() {
  const { clinicSlug } = useParams()
  return (
    <main id="main-content" className="space-y-4 px-5 py-12 sm:px-8 sm:py-16">
      <p className="text-xs font-semibold tracking-widest text-muted-foreground uppercase">Clinic preview</p>
      <h1 className="text-4xl font-semibold tracking-tight sm:text-6xl">Care starts here.</h1>
      <p className="break-words">Clinic: {clinicSlug}</p>
      <p className="text-muted-foreground">Clinic branding and booking will be added in the storefront task.</p>
      <Button asChild><Link to="/patient">Explore the patient portal</Link></Button>
    </main>
  )
}
