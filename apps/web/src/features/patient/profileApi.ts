import { apiFetch } from '../../lib/api'
import { accessToken } from '../clinics/api'

export type PatientProfile = {
  subject_id: string
  name: string
  phone_number: string
  address_line: string
  postal_code: string
  country_code: 'SG'
}

export async function readPatientProfile(
  signal?: AbortSignal,
): Promise<PatientProfile> {
  return (
    await apiFetch('/identity/me/patient-profile', {
      accessToken: await accessToken(),
      signal,
    })
  ).json()
}

export async function savePatientProfile(
  profile: PatientProfile,
): Promise<PatientProfile> {
  const { name, phone_number, address_line, postal_code, country_code } =
    profile
  return (
    await apiFetch('/identity/me/patient-profile', {
      method: 'PUT',
      accessToken: await accessToken(),
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name,
        phone_number,
        address_line,
        postal_code,
        country_code,
      }),
    })
  ).json()
}
