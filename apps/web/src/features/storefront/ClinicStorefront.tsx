import type { CSSProperties } from 'react'
import { ArrowLeft } from 'lucide-react'
import { ClinicHeader } from './ClinicHeader'
import { ClinicIntro } from './ClinicIntro'
import { ConsultationCard } from './ConsultationCard'
import { DoctorList } from './DoctorList'
import { ClinicFooter } from './ClinicFooter'
import { ClinicUnavailable } from './ClinicUnavailable'
import { findClinic } from './fixtures'

export function ClinicStorefront({ slug }: { slug: string | undefined }) {
  const clinic = findClinic(slug)
  if (!clinic) return <ClinicUnavailable />

  const brand = { '--clinic-color': clinic.branding.primary_color } as CSSProperties

  return (
    <div style={brand} className="min-h-screen bg-[#f7f8f5] text-slate-900">
      <div className="h-1.5 bg-[var(--clinic-color)]" />
      <ClinicHeader clinic={clinic} />
      <main className="mx-auto max-w-6xl px-6 pb-16 sm:px-8">
        <div className="mt-6 flex flex-wrap items-center justify-between gap-2 text-xs text-slate-600">
          <a href="/" className="flex items-center gap-2 underline-offset-4 hover:underline"><ArrowLeft className="size-3.5" aria-hidden="true" /> Explore clinics</a>
          <span className="rounded-full border border-slate-200 bg-white px-3 py-1.5">Demo preview · Sample clinic data</span>
        </div>
        <section aria-labelledby="clinic-heading" className="grid gap-10 py-12 lg:grid-cols-[1.4fr_1fr] lg:gap-16 lg:py-20">
          <ClinicIntro clinic={clinic} />
          <ConsultationCard price={clinic.consultation_price} />
        </section>
        <DoctorList doctors={clinic.doctors} />
      </main>
      <ClinicFooter name={clinic.name} />
    </div>
  )
}
