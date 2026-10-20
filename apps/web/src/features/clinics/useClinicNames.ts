import { useQuery } from '@tanstack/react-query'
import { readSession } from '@/auth/session'
import { readClinic } from '../clinic-profile/logo-api'
import { listClinics } from './api'

// Clinic administrators can read their own clinics (including pending ones);
// other roles use the public directory, which lists active clinics only.
async function clinicNames(ids: string[], admin: boolean) {
  if (admin) {
    const clinics = await Promise.all(ids.map(readClinic))
    return new Map(clinics.map((clinic) => [clinic.tenant_id, clinic.name]))
  }
  const names = new Map<string, string>()
  let cursor: string | null = null
  do {
    const page = await listClinics(cursor)
    for (const clinic of page.items) names.set(clinic.tenant_id, clinic.name)
    cursor = page.next_cursor
  } while (cursor && ids.some((id) => !names.has(id)))
  return names
}

/** Returns a label for each clinic ID, falling back to the ID while loading or if unavailable. */
export function useClinicNames(ids: string[], admin = false) {
  const names = useQuery({
    queryKey: ['clinic-names', readSession()?.accessToken, admin, ids],
    queryFn: () => clinicNames(ids, admin),
    enabled: ids.length > 0,
    retry: false,
  })
  return (id: string) => names.data?.get(id) ?? id
}
