import type { Identity } from '@/auth/identity'
import type { Route, Role } from '@/navigation/access'
import { hasRole, rolePaths } from '@/navigation/access'
import {
  Building2,
  Check,
  ChevronDown,
  ShieldCheck,
  Stethoscope,
  UserRound,
} from 'lucide-react'
import { DropdownMenu } from 'radix-ui'

const workspaces = [
  { role: 'patient', label: 'Patient care', icon: UserRound },
  { role: 'doctor', label: 'Doctor workspace', icon: Stethoscope },
  { role: 'clinic_admin', label: 'Clinic administration', icon: Building2 },
  {
    role: 'platform_admin',
    label: 'Platform administration',
    icon: ShieldCheck,
  },
] satisfies { role: Role; label: string; icon: typeof Stethoscope }[]

export function WorkspaceSwitcher({
  identity,
  route,
}: {
  identity: Identity
  route: Route
}) {
  const doctor = hasRole(identity, 'doctor')
  const registration = route.kind === 'doctor-application' && !doctor
  const current = doctor
    ? 'Doctor workspace'
    : registration
      ? 'Doctor registration'
      : 'Choose workspace'
  return (
    <DropdownMenu.Root>
      <DropdownMenu.Trigger
        className="inline-flex min-h-10 items-center gap-2 rounded-lg border border-slate-200 bg-slate-50 px-3 text-sm font-medium text-slate-800 transition-colors hover:bg-slate-100 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal-600"
        aria-label={`Switch workspace. Current: ${current}`}
      >
        <Stethoscope size={17} className="text-teal-700" aria-hidden="true" />
        {current}
        <ChevronDown size={15} className="text-slate-500" aria-hidden="true" />
      </DropdownMenu.Trigger>
      <DropdownMenu.Portal>
        <DropdownMenu.Content
          align="end"
          sideOffset={8}
          className="z-50 w-72 rounded-xl border border-slate-200 bg-white p-2 shadow-xl"
        >
          <DropdownMenu.Label className="px-3 py-2 text-xs font-semibold tracking-wide text-slate-500 uppercase">
            Switch workspace
          </DropdownMenu.Label>
          {workspaces
            .filter((workspace) => hasRole(identity, workspace.role))
            .map(({ role, label, icon: Icon }) => (
              <DropdownMenu.Item key={role} asChild>
                <a
                  href={rolePaths[role]}
                  aria-current={
                    role === 'doctor' && doctor ? 'location' : undefined
                  }
                  className="flex min-h-11 items-center gap-3 rounded-lg px-3 text-sm text-slate-700 outline-none data-[highlighted]:bg-teal-50 data-[highlighted]:text-teal-900"
                >
                  <Icon size={17} aria-hidden="true" />
                  <span className="flex-1">{label}</span>
                  {role === 'doctor' && doctor && (
                    <Check
                      size={16}
                      className="text-teal-700"
                      aria-hidden="true"
                    />
                  )}
                </a>
              </DropdownMenu.Item>
            ))}
          {!doctor && (
            <DropdownMenu.Item asChild>
              <a
                href="/join-as-doctor"
                aria-current={registration ? 'location' : undefined}
                className="flex min-h-11 items-center gap-3 rounded-lg px-3 text-sm text-slate-700 outline-none data-[highlighted]:bg-teal-50 data-[highlighted]:text-teal-900"
              >
                <Stethoscope size={17} aria-hidden="true" />
                <span className="flex-1">Doctor registration</span>
                {registration && (
                  <Check
                    size={16}
                    className="text-teal-700"
                    aria-hidden="true"
                  />
                )}
              </a>
            </DropdownMenu.Item>
          )}
          <DropdownMenu.Separator className="my-2 h-px bg-slate-100" />
          <DropdownMenu.Item asChild>
            <a
              href="/#clinics"
              className="flex min-h-10 items-center gap-3 rounded-lg px-3 text-sm text-slate-600 outline-none data-[highlighted]:bg-slate-100"
            >
              <Building2 size={17} aria-hidden="true" />
              Browse clinics
            </a>
          </DropdownMenu.Item>
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  )
}
