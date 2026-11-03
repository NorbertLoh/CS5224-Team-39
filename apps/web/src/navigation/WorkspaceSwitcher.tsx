import type { Identity } from '@/auth/identity'
import type { Route } from '@/navigation/access'
import {
  availableWorkspaces,
  currentWorkspace,
  workspaceHref,
  workspaceLabels,
} from '@/navigation/workspaces'
import {
  Building2,
  Check,
  ChevronDown,
  ShieldCheck,
  Stethoscope,
  UserRound,
  LayoutGrid,
} from 'lucide-react'
import { DropdownMenu } from 'radix-ui'

const icons = {
  patient: UserRound,
  doctor: Stethoscope,
  clinic_admin: Building2,
  platform_admin: ShieldCheck,
}
const itemClass =
  'flex min-h-11 items-center gap-3 rounded-lg px-3 text-sm text-slate-700 outline-none data-[highlighted]:bg-teal-50 data-[highlighted]:text-teal-900'
const triggerClass =
  'inline-flex min-h-10 max-w-full items-center gap-2 rounded-lg border border-slate-200 bg-slate-50 px-3 text-sm font-medium text-slate-800 transition-colors hover:bg-slate-100 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal-600'

export function WorkspaceSwitcher({
  identity,
  route,
}: {
  identity: Identity
  route: Route
}) {
  const roles = availableWorkspaces(identity)
  if (roles.length === 1 && roles[0] === 'patient') return null
  const current = currentWorkspace(identity, route)
  const registration = current === 'registration'
  const selected = current && current !== 'registration' ? current : undefined
  const label = registration
    ? 'Doctor registration'
    : selected
      ? workspaceLabels[selected]
      : roles.length === 1
        ? workspaceLabels[roles[0]]
        : 'Choose workspace'
  const Icon = registration
    ? Stethoscope
    : selected
      ? icons[selected]
      : roles.length === 1
        ? icons[roles[0]]
        : LayoutGrid
  const applicationClinic =
    typeof window === 'undefined'
      ? null
      : new URLSearchParams(window.location.search).get('clinic')
  const href = (role: (typeof roles)[number]) =>
    workspaceHref(identity, role, route, applicationClinic)
  return (
    <DropdownMenu.Root>
      <DropdownMenu.Trigger
        className={triggerClass}
        aria-label={`Switch workspace. Current: ${label}`}
      >
        <Icon size={17} className="text-teal-700" aria-hidden="true" />
        {label}
        <ChevronDown size={15} className="text-slate-500" aria-hidden="true" />
      </DropdownMenu.Trigger>
      <DropdownMenu.Portal>
        <DropdownMenu.Content
          align="end"
          sideOffset={8}
          className="z-50 w-72 max-w-[calc(100vw-2rem)] rounded-xl border border-slate-200 bg-white p-2 shadow-xl"
        >
          <DropdownMenu.Label className="px-3 py-2 text-xs font-semibold tracking-wide text-slate-500 uppercase">
            Switch workspace
          </DropdownMenu.Label>
          {roles.map((role) => {
            const RoleIcon = icons[role]
            return (
              <DropdownMenu.Item key={role} asChild>
                <a
                  href={href(role)}
                  aria-current={selected === role ? 'location' : undefined}
                  className={itemClass}
                >
                  <RoleIcon size={17} aria-hidden="true" />
                  <span className="flex-1">{workspaceLabels[role]}</span>
                  {selected === role && (
                    <Check
                      size={16}
                      className="text-teal-700"
                      aria-hidden="true"
                    />
                  )}
                </a>
              </DropdownMenu.Item>
            )
          })}
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
