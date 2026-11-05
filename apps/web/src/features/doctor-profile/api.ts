import { accessToken } from '@/auth/access-token'
import { apiFetch } from '@/lib/api'
import { apiBaseUrl } from '@/lib/backend-config'

export type DoctorProfile = { doctor_id: string; photo_id: string | null }

export function doctorPhotoUrl(doctorId: string, photoId: string) {
  return `${apiBaseUrl()}/identity/doctors/${encodeURIComponent(doctorId)}/photos/${encodeURIComponent(photoId)}`
}

export async function doctorProfile(): Promise<DoctorProfile> {
  return (
    await apiFetch('/identity/me/doctor-profile', {
      accessToken: await accessToken(),
    })
  ).json()
}

export async function uploadDoctorPhoto(file: File): Promise<DoctorProfile> {
  return (
    await apiFetch('/identity/me/doctor-profile/photo', {
      method: 'PUT',
      accessToken: await accessToken(),
      headers: { 'Content-Type': file.type },
      body: file,
    })
  ).json()
}

export async function removeDoctorPhoto() {
  await apiFetch('/identity/me/doctor-profile/photo', {
    method: 'DELETE',
    accessToken: await accessToken(),
  })
}
