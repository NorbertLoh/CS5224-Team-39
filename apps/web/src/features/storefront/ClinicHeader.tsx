import type { Clinic } from '@/features/clinics/api'
import { apiBaseUrl, usesAws } from '@/lib/backend-config'
import { ArrowUpRight, HeartPulse } from 'lucide-react'

export function ClinicHeader({ clinic }: { clinic: Clinic }) {
  return (
    <header className="border-b border-slate-200 bg-white">
      <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-5 px-6 py-5 sm:px-8">
        <a
          href={`/clinics/${clinic.slug}`}
          className="flex items-center gap-3 rounded-md focus-visible:outline-2 focus-visible:outline-offset-4"
        >
          <span
            className="relative flex size-11 items-center justify-center overflow-hidden rounded-xl bg-[var(--clinic-color)] text-white"
            aria-hidden="true"
          >
            <HeartPulse className="size-6" />
            {clinic.branding.logo_url && (
              <img
                src={
                  usesAws()
                    ? clinic.branding.logo_url
                    : `${apiBaseUrl()}/tenant/clinics/${clinic.tenant_id}/public-logo`
                }
                alt=""
                className="absolute inset-0 size-full bg-white object-contain"
                onError={(event) => {
                  event.currentTarget.hidden = true
                }}
              />
            )}
          </span>
          <span className="text-lg font-semibold tracking-tight">
            {clinic.name}
          </span>
        </a>
        <nav
          aria-label="Clinic navigation"
          className="flex items-center gap-6 text-sm font-medium"
        >
          <a href="#doctors" className="underline-offset-4 hover:underline">
            Our doctors
          </a>
          <a
            href="/"
            className="flex items-center gap-1 underline-offset-4 hover:underline"
          >
            All clinics <ArrowUpRight className="size-4" aria-hidden="true" />
          </a>
        </nav>
      </div>
    </header>
  )
}
