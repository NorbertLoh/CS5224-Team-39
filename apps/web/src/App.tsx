import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { AuthControls } from './auth/AuthControls'
import { ClinicStorefront } from './features/storefront/ClinicStorefront'
import { storefrontClinics, consultationPrice } from './features/storefront/fixtures'
import { ClinicProfileEditor } from './features/clinic-profile/ClinicProfileEditor'

export default function App() {
  if (window.location.pathname.startsWith('/clinic-admin/')) {
    const route = /^\/clinic-admin\/clinics\/([^/]+)\/profile\/?$/.exec(window.location.pathname)
    return <ClinicProfileEditor slug={route?.[1]} />
  }
  if (window.location.pathname.startsWith('/clinics/')) {
    const route = /^\/clinics\/([^/]+)\/?$/.exec(window.location.pathname)
    return <ClinicStorefront slug={route?.[1]} />
  }

  return (
    <div className="mx-auto max-w-6xl">
      <header className="flex flex-wrap items-center justify-between gap-4 border-b px-5 py-6 sm:px-8">
        <span className="text-xl font-semibold tracking-tight">TeleLink Health</span>
        <Badge variant="secondary">Prototype preview</Badge>
        <AuthControls />
      </header>
      <main className="px-5 py-12 sm:px-8 sm:py-16">
        <p className="text-xs font-semibold tracking-widest text-muted-foreground uppercase">Connected care</p>
        <h1 className="mt-4 max-w-3xl text-4xl leading-tight font-semibold tracking-tight sm:text-6xl">Your clinic, wherever you are.</h1>
        <p className="mt-4 max-w-2xl text-lg text-muted-foreground">A shared home for patients, doctors and clinic teams.</p>
        <section aria-labelledby="clinics-heading" className="mt-10">
          <h2 id="clinics-heading" className="text-2xl font-semibold tracking-tight">Explore our demo clinics</h2>
          <p className="mt-2 text-sm text-muted-foreground">Sample clinic storefronts. Booking is coming soon.</p>
          <div className="mt-5 grid gap-5 sm:grid-cols-2">
            {storefrontClinics.map(clinic => (
              <a key={clinic.tenant_id} href={`/clinics/${clinic.slug}`} className="rounded-xl border border-t-4 p-6 transition-colors hover:bg-muted/50 focus-visible:outline-2 focus-visible:outline-offset-4" style={{ borderTopColor: clinic.branding.primary_color }}>
                <h3 className="text-lg font-semibold">{clinic.name}</h3>
                <p className="mt-2 text-sm text-muted-foreground">Consultation · {consultationPrice(clinic.consultation_price.amount_minor, clinic.consultation_price.currency)} SGD</p>
                <p className="mt-5 text-sm font-medium underline underline-offset-4">View clinic →</p>
              </a>
            ))}
          </div>
        </section>
        <div className="mt-10 grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
          {['Patient', 'Doctor', 'Clinic administrator', 'Platform administrator'].map(role => (
            <Card key={role}>
              <CardHeader><CardTitle><h2>{role}</h2></CardTitle></CardHeader>
              <CardContent>{role === 'Clinic administrator' ? (
                <ul className="space-y-2 text-sm">
                  {storefrontClinics.map(clinic => <li key={clinic.tenant_id}><a href={`/clinic-admin/clinics/${clinic.slug}/profile`} className="underline underline-offset-4">Edit {clinic.name} demo</a></li>)}
                </ul>
              ) : <p className="text-muted-foreground">Portal pages are coming next.</p>}</CardContent>
            </Card>
          ))}
        </div>
      </main>
    </div>
  )
}
