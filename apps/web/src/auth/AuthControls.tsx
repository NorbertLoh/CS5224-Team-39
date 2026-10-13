import { useEffect, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import {
  authConfig,
  beginLogin,
  clearSession,
  endSession,
  finishLogin,
  readSession,
  refreshSession,
} from './session'
import type { Session } from './session'
import { Button } from '../components/ui/button'

// A single callback exchange survives React StrictMode's effect replay.
let callback: Promise<Session> | undefined
const callbackSearch =
  location.pathname === '/auth/callback' ? location.search : null
const logoutWarning = sessionStorage.getItem('telelink.logout-warning') || ''
sessionStorage.removeItem('telelink.logout-warning')

export function AuthControls() {
  const queryClient = useQueryClient()
  const [session, setSession] = useState(readSession)
  const [message, setMessage] = useState(logoutWarning)
  const [busy, setBusy] = useState(false)
  let config: ReturnType<typeof authConfig> = null
  let configurationError = ''
  try {
    config = authConfig()
  } catch (error) {
    configurationError = (error as Error).message
  }
  const configured = Boolean(config)

  useEffect(() => {
    if (!configured || callbackSearch === null) return
    const settings = authConfig()!
    callback ??= finishLogin(settings, callbackSearch)
    // Strip OAuth credentials from address bar/history immediately.
    history.replaceState(null, '', '/')
    let active = true
    callback
      .then((value) => {
        if (active) {
          queryClient.clear()
          setSession(value)
          setMessage('Signed in.')
        }
      })
      .catch(() => {
        if (active) {
          clearSession()
          queryClient.clear()
          setSession(null)
          setMessage('Sign-in failed or expired. Please try again.')
        }
      })
    return () => {
      active = false
    }
  }, [configured, queryClient])

  useEffect(() => {
    if (!configured || !session) return
    let active = true
    let refreshing = false
    const check = async () => {
      if (!active || refreshing || session.expiresAt - Date.now() > 60000)
        return
      refreshing = true
      try {
        const refreshed = await refreshSession(authConfig()!, session)
        if (active) setSession(refreshed)
      } catch {
        if (active) {
          clearSession()
          queryClient.clear()
          setSession(null)
          setMessage('Your session expired. Please sign in again.')
        }
      } finally {
        refreshing = false
      }
    }
    const timer = window.setInterval(() => {
      void check()
    }, 5000)
    window.addEventListener('focus', check)
    void check()
    return () => {
      active = false
      clearInterval(timer)
      window.removeEventListener('focus', check)
    }
  }, [configured, queryClient, session])

  async function login() {
    setBusy(true)
    try {
      location.assign(await beginLogin(config!))
    } catch {
      setBusy(false)
      setMessage('Unable to start sign-in. Please try again.')
    }
  }
  async function logout() {
    setBusy(true)
    queryClient.clear()
    setSession(null)
    location.assign(await endSession(config!, session))
  }
  if (!configured)
    return (
      <p role="status" className="text-sm text-muted-foreground">
        {configurationError || 'Configure Cognito to enable sign-in.'}
      </p>
    )
  return (
    <div className="flex flex-wrap items-center gap-3">
      <span role="status" className="text-sm">
        {message || (session ? 'Signed in' : 'Signed out')}
      </span>
      <Button
        disabled={busy}
        onClick={() => {
          void (session ? logout() : login())
        }}
      >
        {session ? 'Sign out' : 'Sign in'}
      </Button>
    </div>
  )
}
