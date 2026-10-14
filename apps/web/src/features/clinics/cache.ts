import type { QueryClient } from '@tanstack/react-query'

// Clinic edits affect public listings and every administration view.
export async function refreshClinicViews(client: QueryClient) {
  await Promise.all([
    'clinics', 'public-clinic', 'clinic-profile', 'managed-clinics',
    'platform-clinics', 'platform-clinic',
  ].map(key => client.invalidateQueries({ queryKey: [key] })))
}
