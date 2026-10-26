import { Button } from '@/components/ui/button'
import type { Clinic } from '@/features/clinics/api'
import { ArrowUpRight, Video } from 'lucide-react'

export function ClinicIntro({ clinic }: { clinic: Clinic }) {
  return (
    <div>
      <p className="flex items-center gap-2 text-xs font-semibold tracking-[0.16em] uppercase">
        <span className="size-2 rounded-full bg-[var(--clinic-color)]" /> Care,
        wherever you are
      </p>
      <h1
        id="clinic-heading"
        className="mt-5 max-w-2xl text-4xl leading-[1.08] font-semibold tracking-tight sm:text-6xl"
      >
        Your next step to
        <br />
        feeling better.
      </h1>
      <p className="mt-6 text-lg font-medium">Welcome to {clinic.name}.</p>
      <p className="mt-2 max-w-lg leading-relaxed text-slate-600">
        {clinic.branding.description}
      </p>
      <Button asChild size="lg" className="mt-7 h-11 px-5">
        <a href="#doctors">
          Meet our doctors <ArrowUpRight aria-hidden="true" />
        </a>
      </Button>
      <div className="mt-9 flex items-center gap-3 border-t border-slate-200 pt-5 text-sm text-slate-600">
        <Video
          className="size-5 text-[var(--clinic-color)]"
          aria-hidden="true"
        />{' '}
        Online consultations, through TeleLink Health
      </div>
    </div>
  )
}
