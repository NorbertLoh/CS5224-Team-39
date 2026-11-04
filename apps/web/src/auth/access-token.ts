import { authConfig, readSession, refreshSession } from '@/auth/session'

export async function accessToken() {
  let session = readSession()
  if (!session) throw new Error('Sign in to continue.')
  if (session.expiresAt - Date.now() < 60000) {
    const config = authConfig()
    if (!config) throw new Error('Sign-in is not configured.')
    session = await refreshSession(config, session)
  }
  return session.accessToken
}
