import type { Identity } from '@/auth/identity'
import { useVerificationAttention } from '@/navigation/useNavigationAttention'
import { useClinicNames } from '@/features/clinics/hooks/useClinicNames'
import type { Route } from '@/navigation/access'
import { doctorNavigationState } from '@/navigation/doctor-navigation'
import { WorkspaceNavigation } from '@/navigation/WorkspaceNavigation'
import {
  Building2,
  CalendarDays,
  Clock3,
  ShieldCheck,
  Stethoscope,
  UserRound,
} from 'lucide-react'

export function DoctorNavigation({
  route,
  identity,
}: {
  route: Route
  identity: Identity
}) {
  const attention = useVerificationAttention()
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
          {
            href: '/doctor/profile',
            label: 'Profile',
            section: 'profile',
            icon: UserRound,
          },
        ]
      : []),
    {
      href: state.verification,
      label: state.canPractise ? 'Verification' : 'Application status',
      section: 'verification',
      icon: ShieldCheck,
    },
  ]
  return (
    <WorkspaceNavigation
      title={state.canPractise ? 'Doctor workspace' : 'Doctor application'}
      description={
        state.section === 'consultation'
          ? 'Consultation'
          : state.canPractise
            ? 'Your appointments, schedule and professional details'
            : 'Apply and track your licence verification'
      }
      icon={Stethoscope}
      links={pages.map(({ section, ...page }) => ({
        ...page,
        active: section === state.section,
        attention: section === 'verification' ? attention : undefined,
      }))}
    >
      {state.canPractise && state.section === 'verification' && (
        <p className="text-xs text-slate-500">
          Verification covers all your clinics.
        </p>
      )}
      {state.canPractise &&
        state.section !== 'consultation' &&
        state.section !== 'profile' &&
        state.section !== 'verification' && (
          <label className="flex min-w-0 max-w-full items-center gap-2 text-xs font-medium text-slate-500">
            <Building2 size={16} aria-hidden="true" />
            <span>Clinic</span>
            <select
              aria-label="Doctor clinic"
              value={state.clinicId ?? ''}
              className="min-h-10 min-w-0 max-w-64 flex-1 rounded-lg border border-slate-200 bg-white px-3 text-sm text-slate-800 focus-visible:outline-2 focus-visible:outline-teal-600"
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
    </WorkspaceNavigation>
  )
}
