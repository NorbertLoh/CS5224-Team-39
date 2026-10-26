import { ApiError } from '@/lib/api'

export function recordsError(error: unknown) {
  if (error instanceof ApiError) {
    if (error.status === 401)
      return 'Your session expired. Please sign in again.'
    if (error.status === 403 || error.status === 404)
      return 'This record or appointment is unavailable to your account.'
    if (error.status === 409)
      return 'The appointment, prescription or catalogue changed. Reload records before continuing.'
    if (error.status === 422)
      return 'Check the note, medications, quantities, instructions and MC dates/duration.'
  }
  return 'Could not complete the records request. Check your connection and reload records. If a save or issuance timed out, reload to check its outcome before trying again.'
}
