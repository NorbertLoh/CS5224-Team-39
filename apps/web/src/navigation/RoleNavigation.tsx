import type { Identity } from '../features/clinics/api'
import { clinicIds, hasRole, roleLabels, rolePaths } from './access'
import type { Role, Route } from './access'

const roles: Role[] = ['patient', 'doctor', 'clinic_admin', 'platform_admin']

export function RoleNavigation({ identity, route }: { identity: Identity; route: Route }) {
  const role = 'role' in route ? route.role : undefined
  const tenantId = 'tenantId' in route ? route.tenantId : undefined
  const ids = role === 'doctor' || role === 'clinic_admin' ? clinicIds(identity, role) : []
  return <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-5 px-6 py-4">
    <nav aria-label="Your roles" className="flex flex-wrap gap-5 text-sm">
      {roles.filter(item => hasRole(identity, item)).map(item => <a key={item} href={rolePaths[item]} aria-current={item === role ? 'page' : undefined} className="underline underline-offset-4">{roleLabels[item]}</a>)}
    </nav>
    {ids.length > 0 && <label className="grid min-w-0 max-w-full gap-2 text-sm">Selected clinic
      <select className="min-w-0 max-w-full rounded-md border bg-white p-2" value={ids.includes(tenantId ?? '') ? tenantId : ''} onChange={event => {
        const id = event.target.value
        if (!ids.includes(id)) return
        const suffix = route.kind === 'staff' ? 'staff' : 'profile'
        window.location.assign(role === 'doctor' ? `/doctor/clinics/${id}` : `/clinic-admin/clinics/${id}/${suffix}`)
      }}>
        <option value="" disabled>Choose a clinic</option>
        {ids.map(id => <option key={id} value={id}>Clinic {id}</option>)}
      </select>
    </label>}
  </div>
}
