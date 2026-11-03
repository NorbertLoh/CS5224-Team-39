import type { Identity } from '@/auth/identity'
import { useClinicNames } from '@/features/clinics/hooks/useClinicNames'
import type { Route } from '@/navigation/access'
import { doctorNavigationState } from '@/navigation/doctor-navigation'
import { tabClassName } from '@/lib/tab-styles'
import {
  Building2,
  CalendarDays,
  Clock3,
  ShieldCheck,
  Stethoscope,
} from 'lucide-react'

export function DoctorNavigation({
  route,
  identity,
}: {
  route: Route
  identity: Identity
}) {
  const applicationClinic =
    typeof window === 'undefined'
      ? null
      : new URLSearchParams(window.location.search).get('clinic')
  const state = doctorNavigationState(identity, route, applicationClinic)
  const clinicName = useClinicNames(state.clinics)
  const pages = [
    ...(state.canPractise
      ? [
          {
            href: state.base,
            label: 'Appointments',
            section: 'appointments',
            icon: CalendarDays,
          },
          {
            href: `${state.base}/availability`,
            label: 'Availability',
            section: 'availability',
            icon: Clock3,
          },
        ]
      : []),
    {
      href: state.verification,
      label: 'Verification',
      section: 'verification',
      icon: ShieldCheck,
    },
  ]
  return (
    <div className="border-t border-slate-100 bg-slate-50/70">
      <div className="mx-auto flex max-w-6xl flex-col gap-4 px-6 py-4 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex items-center gap-3">
          <span className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-teal-100 text-teal-800">
            <Stethoscope size={21} aria-hidden="true" />
          </span>
          <div>
            <p className="text-sm font-semibold text-slate-900">
              {state.canPractise ? 'Doctor workspace' : 'Doctor registration'}
            </p>
            <p className="text-xs text-slate-500">
              {state.section === 'consultation'
                ? 'Consultation'
                : state.section === 'verification' && state.canPractise
                  ? 'Professional details and licence'
                  : state.canPractise
                    ? 'Your appointments and schedule'
                    : 'Application and licence verification'}
            </p>
          </div>
        </div>
        <nav
          aria-label="Doctor workspace"
          className="flex flex-wrap gap-1 border-b border-slate-200"
        >
          {pages.map(({ href, label, section, icon: Icon }) => {
            const active = section === state.section
            return (
              <a
                key={href}
                href={href}
                aria-current={active ? 'page' : undefined}
                className={tabClassName(active)}
              >
                <Icon
                  size={17}
                  className="hidden sm:block"
                  aria-hidden="true"
                />
                {label}
              </a>
            )
          })}
        </nav>
        {state.canPractise && state.section === 'verification' && (
          <p className="text-xs text-slate-500">
            Verification covers all your clinics.
          </p>
        )}
        {state.canPractise &&
          state.section !== 'consultation' &&
          state.section !== 'verification' && (
            <label className="flex min-w-0 items-center gap-2 text-xs font-medium text-slate-500">
              <Building2 size={16} aria-hidden="true" />
              <span>Clinic</span>
              <select
                aria-label="Doctor clinic"
                value={state.clinicId ?? ''}
                className="min-h-10 min-w-0 flex-1 rounded-lg border border-slate-200 bg-white px-3 text-sm text-slate-800 focus-visible:outline-2 focus-visible:outline-teal-600 lg:max-w-56"
                onChange={(event) => {
                  const clinic = event.target.value
                  const base = clinic ? `/doctor/clinics/${clinic}` : '/doctor'
                  window.location.assign(
                    state.section === 'availability'
                      ? `${base}/availability`
                      : base,
                  )
                }}
              >
                {state.section !== 'availability' && (
                  <option value="">All clinics</option>
                )}
                {state.clinics.map((id, index) => (
                  <option key={id} value={id}>
                    {clinicName(id) === id
                      ? `Clinic ${index + 1}`
                      : clinicName(id)}
                  </option>
                ))}
              </select>
            </label>
          )}
      </div>
    </div>
  )
}
