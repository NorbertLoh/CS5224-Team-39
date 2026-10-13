import { useCallback, useEffect, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { Button } from '../components/ui/button'
import { authConfig, beginLogin, clearSession, endSession, finishLogin, readSession, refreshSession } from './session'
import type { AuthConfig, Session } from './session'

// Configuration is fixed for this Vite build. Callback work is shared across StrictMode mounts.
let config: AuthConfig | null = null
let configurationError = ''
try {
  config = authConfig()
} catch (error) {
  configurationError = (error as Error).message
}
const callbackSearch = location.pathname === '/auth/callback' ? location.search : null
let callback: Promise<Session> | undefined
const logoutWarning = sessionStorage.getItem('telelink.logout-warning') || ''
sessionStorage.removeItem('telelink.logout-warning')

export function AuthControls() {
  const queryClient = useQueryClient()
  const [session, setSession] = useState(readSession)
  const [message, setMessage] = useState(logoutWarning)
  const [busy, setBusy] = useState(false)

  const signOut = useCallback(
    (notice = '') => {
      clearSession()
      queryClient.clear()
      setSession(null)
      setMessage(notice)
    },
    [queryClient],
  )

  useEffect(() => {
    if (!config || callbackSearch === null) return
    callback ??= finishLogin(config, callbackSearch)
    history.replaceState(null, '', '/')
    let cancelled = false
    callback
      .then((value) => {
        if (cancelled) return
        queryClient.clear()
        setSession(value)
        setMessage('Signed in.')
      })
      .catch(() => {
        if (!cancelled) signOut('Sign-in failed or expired. Please try again.')
      })
    return () => {
      cancelled = true
    }
  }, [queryClient, signOut])

  useEffect(() => {
    const settings = config
    if (!settings || !session) return
    let cancelled = false
    const check = async () => {
      if (cancelled || session.expiresAt - Date.now() > 60000) return
      try {
        const renewed = await refreshSession(settings, session)
        if (!cancelled) setSession(renewed)
      } catch {
        if (!cancelled) signOut('Your session expired. Please sign in again.')
      }
    }
    const timer = window.setInterval(check, 5000)
    window.addEventListener('focus', check)
    void check()
    return () => {
      cancelled = true
      clearInterval(timer)
      window.removeEventListener('focus', check)
    }
  }, [session, signOut])

  async function handleClick() {
    if (!config) return
    setBusy(true)
    try {
      if (session) {
        signOut()
        location.assign(await endSession(config, session))
      } else {
        location.assign(await beginLogin(config))
      }
    } catch {
      setBusy(false)
      setMessage('Unable to complete sign-in or sign-out. Please try again.')
    }
  }

  if (!config)
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
          void handleClick()
        }}
      >
        {session ? 'Sign out' : 'Sign in'}
      </Button>
    </div>
  )
}
