import type { Identity } from '@/auth/identity'
import type { Role, Route } from '@/navigation/access'
import { hasRole, roleLabels, rolePaths } from '@/navigation/access'

const roles: Role[] = ['patient', 'doctor', 'clinic_admin', 'platform_admin']

export function RoleNavigation({
  identity,
  route,
}: {
  identity: Identity
  route: Route
}) {
  const role = 'role' in route ? route.role : undefined
  return (
    <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-5 px-6 py-4">
      <nav aria-label="Your roles" className="flex flex-wrap gap-5 text-sm">
        {roles
          .filter((item) => hasRole(identity, item))
          .map((item) => (
            <a
              key={item}
              href={rolePaths[item]}
              aria-current={item === role ? 'page' : undefined}
              className="underline underline-offset-4"
            >
              {roleLabels[item]}
            </a>
          ))}
      </nav>
    </div>
  )
}
