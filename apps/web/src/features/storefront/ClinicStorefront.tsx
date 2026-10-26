import { ErrorState } from '@/components/ErrorState'
import { LoadingState } from '@/components/LoadingState'
import { publicClinic } from '@/features/clinics/api'
import { ClinicFooter } from '@/features/storefront/ClinicFooter'
import { ClinicHeader } from '@/features/storefront/ClinicHeader'
import { ClinicIntro } from '@/features/storefront/ClinicIntro'
import { ClinicUnavailable } from '@/features/storefront/ClinicUnavailable'
import { ConsultationCard } from '@/features/storefront/ConsultationCard'
import { DoctorDirectory } from '@/features/storefront/DoctorDirectory'
import { ApiError } from '@/lib/api'
import { useQuery } from '@tanstack/react-query'
import { ArrowLeft } from 'lucide-react'
import type { CSSProperties } from 'react'

export function ClinicStorefront({ slug }: { slug: string | undefined }) {
  const query = useQuery({
    queryKey: ['public-clinic', slug],
    queryFn: () => publicClinic(slug!),
    enabled: Boolean(slug),
  })
  if (!slug || (query.error instanceof ApiError && query.error.status === 404))
    return <ClinicUnavailable />
  if (query.isPending) return <LoadingState message="Loading clinic..." />
  if (query.isError)
    return (
      <ErrorState
        message="Could not load the clinic."
        onRetry={() => void query.refetch()}
      />
    )
  const clinic = query.data

  const brand = {
    '--clinic-color': clinic.branding.primary_color,
  } as CSSProperties

  return (
    <div style={brand} className="min-h-screen bg-[#f7f8f5] text-slate-900">
      <div className="h-1.5 bg-[var(--clinic-color)]" />
      <ClinicHeader clinic={clinic} />
      <main className="mx-auto max-w-6xl px-6 pb-16 sm:px-8">
        <div className="mt-6 flex flex-wrap items-center justify-between gap-2 text-xs text-slate-600">
          <a
            href="/"
            className="flex items-center gap-2 underline-offset-4 hover:underline"
          >
            <ArrowLeft className="size-3.5" aria-hidden="true" /> Explore
            clinics
          </a>
        </div>
        <section
          aria-labelledby="clinic-heading"
          className="grid gap-10 py-12 lg:grid-cols-[1.4fr_1fr] lg:gap-16 lg:py-20"
        >
          <ClinicIntro clinic={clinic} />
          <ConsultationCard
            price={clinic.consultation_price}
            slug={clinic.slug}
            active={clinic.status === 'active'}
          />
        </section>
        <DoctorDirectory tenantId={clinic.tenant_id} />
      </main>
      <ClinicFooter name={clinic.name} />
    </div>
  )
}
