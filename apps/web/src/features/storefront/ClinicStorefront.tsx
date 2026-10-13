import type { CSSProperties } from 'react'
import { ArrowLeft, ArrowUpRight, HeartPulse, Stethoscope, Video } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { findClinic, consultationPrice } from './fixtures'

export function ClinicStorefront({ slug }: { slug: string | undefined }) {
  const clinic = findClinic(slug)

  if (!clinic) {
    return (
      <main className="mx-auto max-w-xl px-6 py-24">
        <p className="text-sm text-muted-foreground">TeleLink Health</p>
        <h1 className="mt-4 text-3xl font-semibold tracking-tight">Clinic unavailable</h1>
        <p className="mt-3 text-muted-foreground">This clinic could not be found or is not accepting new consultations.</p>
        <Button asChild variant="outline" className="mt-6"><a href="/">Browse clinics</a></Button>
      </main>
    )
  }

  const brand = { '--clinic-color': clinic.branding.primary_color } as CSSProperties

  return (
    <div style={brand} className="min-h-screen bg-[#f7f8f5] text-slate-900">
      <div className="h-1.5 bg-[var(--clinic-color)]" />
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-5 px-6 py-5 sm:px-8">
          <a href={`/clinics/${clinic.slug}`} className="flex items-center gap-3 rounded-md focus-visible:outline-2 focus-visible:outline-offset-4">
            <span className="relative flex size-11 items-center justify-center overflow-hidden rounded-xl bg-[var(--clinic-color)] text-white" aria-hidden="true">
              <HeartPulse className="size-6" />
              {clinic.branding.logo_url && <img src={clinic.branding.logo_url} alt="" className="absolute inset-0 size-full bg-white object-contain" onError={event => { event.currentTarget.hidden = true }} />}
            </span>
            <span className="text-lg font-semibold tracking-tight">{clinic.name}</span>
          </a>
          <nav aria-label="Clinic navigation" className="flex items-center gap-6 text-sm font-medium">
            <a href="#doctors" className="underline-offset-4 hover:underline">Our doctors</a>
            <a href="/" className="flex items-center gap-1 underline-offset-4 hover:underline">All clinics <ArrowUpRight className="size-4" aria-hidden="true" /></a>
          </nav>
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-6 pb-16 sm:px-8">
        <div className="mt-6 flex flex-wrap items-center justify-between gap-2 text-xs text-slate-600">
          <a href="/" className="flex items-center gap-2 underline-offset-4 hover:underline"><ArrowLeft className="size-3.5" aria-hidden="true" /> Explore clinics</a>
          <span className="rounded-full border border-slate-200 bg-white px-3 py-1.5">Demo preview · Sample clinic data</span>
        </div>

        <section aria-labelledby="clinic-heading" className="grid gap-10 py-12 lg:grid-cols-[1.4fr_1fr] lg:gap-16 lg:py-20">
          <div>
            <p className="flex items-center gap-2 text-xs font-semibold tracking-[0.16em] uppercase"><span className="size-2 rounded-full bg-[var(--clinic-color)]" /> Care, wherever you are</p>
            <h1 id="clinic-heading" className="mt-5 max-w-2xl text-4xl leading-[1.08] font-semibold tracking-tight sm:text-6xl">Your next step to<br />feeling better.</h1>
            <p className="mt-6 text-lg font-medium">Welcome to {clinic.name}.</p>
            <p className="mt-2 max-w-lg leading-relaxed text-slate-600">{clinic.branding.description}</p>
            <Button asChild size="lg" className="mt-7 h-11 px-5"><a href="#doctors">Meet our doctors <ArrowUpRight aria-hidden="true" /></a></Button>
            <div className="mt-9 flex items-center gap-3 border-t border-slate-200 pt-5 text-sm text-slate-600">
              <Video className="size-5 text-[var(--clinic-color)]" aria-hidden="true" /> Online consultations, through TeleLink Health
            </div>
          </div>

          <aside aria-labelledby="consultation-heading" className="self-start overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
            <div className="flex items-center gap-3 border-b border-slate-100 p-6 sm:p-8">
              <span className="rounded-xl bg-slate-100 p-3"><Stethoscope className="size-6 text-[var(--clinic-color)]" aria-hidden="true" /></span>
              <div><p className="text-xs text-slate-500">Consultation</p><h2 id="consultation-heading" className="mt-1 font-semibold">A conversation about your health</h2></div>
            </div>
            <div className="p-6 sm:p-8">
              <p className="text-sm text-slate-500">Clinic consultation fee</p>
              <p className="mt-2 text-4xl font-semibold tracking-tight">{consultationPrice(clinic.consultation_price.amount_minor, clinic.consultation_price.currency)} <span className="text-sm font-normal text-slate-500">SGD</span></p>
              <p className="mt-4 text-sm leading-relaxed text-slate-600">Get to know the clinic's doctors below before choosing your consultation.</p>
              <Button disabled className="mt-6 h-11 w-full" aria-describedby="booking-notice">Booking coming soon</Button>
              <p id="booking-notice" className="mt-3 text-xs leading-relaxed text-slate-500">This is a demo storefront. Appointment selection and payment are not available yet.</p>
            </div>
          </aside>
        </section>

        <section id="doctors" aria-labelledby="doctors-heading" className="scroll-mt-6 border-t border-slate-200 pt-10">
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div><p className="text-xs font-semibold tracking-[0.16em] text-slate-500 uppercase">People behind your care</p><h2 id="doctors-heading" className="mt-2 text-2xl font-semibold tracking-tight sm:text-3xl">Meet our doctors</h2></div>
            <p className="text-sm text-slate-500">{clinic.doctors.length} {clinic.doctors.length === 1 ? 'doctor' : 'doctors'} at this clinic</p>
          </div>
          {clinic.doctors.length ? (
            <ul className="mt-6 grid gap-4 sm:grid-cols-2">
              {clinic.doctors.map(doctor => (
                <li key={doctor.doctor_id} className="flex items-center gap-4 rounded-xl border border-slate-200 bg-white p-6">
                  <span className="flex size-12 shrink-0 items-center justify-center rounded-full bg-slate-100 text-[var(--clinic-color)]" aria-hidden="true"><Stethoscope className="size-5" /></span>
                  <div><h3 className="font-semibold">{doctor.display_name}</h3><p className="mt-1 text-sm text-slate-500">Clinic doctor</p></div>
                </li>
              ))}
            </ul>
          ) : <p className="mt-6 text-slate-600">No doctors are listed at this clinic yet.</p>}
        </section>
      </main>

      <footer className="border-t border-slate-200 bg-white">
        <div className="mx-auto flex max-w-6xl flex-wrap justify-between gap-3 px-6 py-6 text-xs text-slate-500 sm:px-8"><span>{clinic.name}</span><span>Powered by <a href="/" className="font-medium text-slate-700 underline-offset-4 hover:underline">TeleLink Health</a></span></div>
      </footer>
    </div>
  )
}
