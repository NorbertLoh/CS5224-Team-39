import { accessToken } from '@/auth/access-token'
import { readSession } from '@/auth/session'
import type { Appointment } from '@/features/scheduling/api'
import { joinEarlyMinutes } from '@/features/video/domain/joinWindow'
import type {
  CallAdmission,
  RoomConnection,
} from '@/features/video/media/connection'
import {
  RoomAccessError,
  validateAdmission,
} from '@/features/video/media/connection'
import { ApiError, apiFetch } from '@/lib/api'

export async function consultationAction(
  id: string,
  action: 'start' | 'complete',
) {
  return (
    await apiFetch(
      `/consultation/appointments/${encodeURIComponent(id)}/${action}`,
      {
        method: 'POST',
        accessToken: await accessToken(),
        signal: AbortSignal.timeout(15000),
      },
    )
  ).json()
}

export function roomEligibility(
  appointment: Appointment,
  role: 'patient' | 'doctor',
  subjectId: string,
  now = Date.now(),
) {
  return (
    appointment[role === 'doctor' ? 'doctor_id' : 'patient_id'] === subjectId &&
    ['confirmed', 'in_progress'].includes(appointment.status) &&
    appointment.payment_resolution === 'confirmed' &&
    Boolean(appointment.payment_id) &&
    Date.parse(appointment.starts_at) - joinEarlyMinutes * 60000 <= now &&
    (appointment.status === 'in_progress' ||
      now < Date.parse(appointment.ends_at))
  )
}

export function consultationError(error: unknown) {
  if (error instanceof ApiError) {
    if (error.code === 'prescription_not_finalized')
      return 'The prescription could not be issued. Check its medications and saved draft before ending the consultation.'
    if (error.status === 401) return 'Your session expired. Sign in again.'
    if (error.status === 409)
      return 'The appointment is not ready or you already have an active call. Leave the other room or wait for its access to expire, then try again.'
    if ([403, 404].includes(error.status))
      return 'Call access is unavailable. Check the appointment time, payment and your current access.'
  }
  return 'Could not connect to the consultation. Check your connection and try again.'
}

export function roomAccessDenied(error: unknown) {
  return (
    error instanceof ApiError &&
    ([401, 403, 404, 422].includes(error.status) ||
      ['admission_denied', 'session_context_conflict'].includes(
        error.code ?? '',
      ))
  )
}

// Same-origin HTTPS keeps admission credentials out of unrelated hosts and logs.
export function bookedRoomConnection(
  appointmentId: string,
  subjectId: string,
  origin = window.location.origin,
): RoomConnection {
  const url = new URL(origin)
  if (url.protocol !== 'https:')
    throw new Error(
      'Open the application through its HTTPS consultation address.',
    )
  return {
    signalling: {
      host: url.hostname,
      port: Number(url.port || 443),
      path: '/peerjs',
      key: 'telelink',
      secure: true,
    },
    async acquire(signal) {
      if (!readSession()) throw new RoomAccessError('Sign in to continue.')
      const response = await apiFetch('/consultation/admissions', {
        method: 'POST',
        accessToken: await accessToken(),
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ appointment_id: appointmentId }),
        signal: AbortSignal.any([signal, AbortSignal.timeout(10000)]),
      }).catch((error: unknown) => {
        if (roomAccessDenied(error))
          throw new RoomAccessError(consultationError(error))
        throw error
      })
      const grant = await response.json()
      if (
        grant.appointment_id !== appointmentId ||
        grant.subject_id !== subjectId
      )
        throw new RoomAccessError('Invalid admission context')
      const path: unknown = grant.signalling_path ?? '/peerjs'
      if (
        typeof path !== 'string' ||
        !/^\/peerjs(?:\/nodes\/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})?$/.test(
          path,
        )
      )
        throw new RoomAccessError('Invalid signalling assignment')
      const admission: CallAdmission = {
        peerId: grant.peer_id,
        token: grant.token,
        expiresAt: Date.parse(grant.expires_at),
        iceServers: grant.ice_servers,
        relayOnly: grant.relay_only,
        signallingPath: path,
      }
      if (!Array.isArray(admission.iceServers))
        throw new Error('Invalid media configuration')
      validateAdmission(admission)
      return admission
    },
    async counterpart(admission, signal) {
      const response = await fetch(
        `${url.origin}${admission.signallingPath ?? '/peerjs'}/counterpart`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            peer_id: admission.peerId,
            token: admission.token,
          }),
          credentials: 'omit',
          cache: 'no-store',
          redirect: 'error',
          signal: AbortSignal.any([signal, AbortSignal.timeout(10000)]),
        },
      )
      if (!response.ok) throw new ApiError(response.status)
      const result = await response.json()
      if (
        result.peer_id !== null &&
        (typeof result.peer_id !== 'string' ||
          !/^[0-9a-f-]{36}$/.test(result.peer_id) ||
          result.peer_id === admission.peerId)
      )
        throw new Error('Invalid participant')
      return result.peer_id as string | null
    },
    async renew(admission, signal) {
      if (!readSession()) throw new RoomAccessError('Sign in to continue.')
      try {
        const response = await apiFetch('/consultation/admissions/renew', {
          method: 'POST',
          accessToken: await accessToken(),
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            peer_id: admission.peerId,
            token: admission.token,
          }),
          signal: AbortSignal.any([signal, AbortSignal.timeout(10000)]),
        })
        const lease = await response.json()
        const expectedNode =
          admission.signallingPath?.split('/nodes/')[1] ?? null
        if (
          lease.peer_id !== admission.peerId ||
          lease.subject_id !== subjectId ||
          lease.appointment_id !== appointmentId ||
          lease.node_id !== expectedNode ||
          typeof lease.expires_at !== 'string'
        )
          throw new RoomAccessError('Invalid active call context')
        return Date.parse(lease.expires_at)
      } catch (error) {
        if (roomAccessDenied(error))
          throw new RoomAccessError(consultationError(error))
        throw error
      }
    },
  }
}
