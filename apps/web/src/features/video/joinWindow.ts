import { usesAws } from '../../lib/backend-config'

export function localJoinEarlyMinutes(env = import.meta.env ?? {}) {
  if (usesAws(env)) return 10
  const value = Number(env.VITE_LOCAL_TEST_JOIN_EARLY_MINUTES ?? 10)
  if (!Number.isInteger(value) || value < 10 || value > 180)
    throw new Error('Local test join window must be 10–180 minutes.')
  return value
}

export const joinEarlyMinutes = localJoinEarlyMinutes()
