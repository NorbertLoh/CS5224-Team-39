import type { Note } from '@/features/records/types'
import { ApiError } from '@/lib/api'
import { base, id, json, request } from './client'

export async function readNote(
  appointmentId: string,
  signal?: AbortSignal,
): Promise<Note | null> {
  try {
    return await (
      await request(`${base}/appointments/${id(appointmentId)}/note`, {
        signal,
      })
    ).json()
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return null
    throw error
  }
}

export async function saveNote(
  appointmentId: string,
  text: string,
): Promise<Note> {
  return (
    await request(
      `${base}/appointments/${id(appointmentId)}/note`,
      json('PUT', { text: text.trim() }),
    )
  ).json()
}
