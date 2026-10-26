import type { MedicalCertificate } from '@/features/records/certificates/medicalCertificate'
import { ApiError } from '@/lib/api'
import { base, id, json, request } from './client'

export async function readMedicalCertificate(
  appointmentId: string,
  signal?: AbortSignal,
): Promise<MedicalCertificate | null> {
  try {
    const result: MedicalCertificate = await (
      await request(
        `${base}/appointments/${id(appointmentId)}/medical-certificate`,
        { signal },
      )
    ).json()
    if (result.appointment_id !== appointmentId)
      throw new Error('Invalid MC context')
    return result
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return null
    throw error
  }
}

export async function saveMedicalCertificate(
  appointmentId: string,
  body: {
    selected: boolean
    start_date: string | null
    duration_days: number | null
    additional_notes: string
  },
): Promise<MedicalCertificate> {
  const result: MedicalCertificate = await (
    await request(
      `${base}/appointments/${id(appointmentId)}/medical-certificate`,
      json('PUT', body),
    )
  ).json()
  if (result.appointment_id !== appointmentId)
    throw new Error('Invalid MC context')
  return result
}
