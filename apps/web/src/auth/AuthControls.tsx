import { useCallback, useEffect, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { Button } from '../components/ui/button'
import { SignInPage } from './SignInPage'
import { accessToken, currentIdentity } from '../features/clinics/api'
import { ApiError, apiFetch } from '../lib/api'
import { defaultWorkspace } from '../navigation/access'
import {
  authConfig,
  beginLogin,
  clearSession,
  endSession,
  finishLogin,
  readSession,
  refreshSession,
  signInWithPassword,
  subscribeToSession,
} from './session'
import type { AuthConfig, Session } from './session'

// Configuration is fixed for this Vite build. Callback work is shared across StrictMode mounts.
let config: AuthConfig | null = null
let configurationError = ''
try {
  config = authConfig()
} catch (error) {
  configurationError = (error as Error).message
}
const callbackSearch =
  location.pathname === '/auth/callback' ? location.search : null
let callback: Promise<Session> | undefined
const logoutWarning = sessionStorage.getItem('telelink.logout-warning') || ''
sessionStorage.removeItem('telelink.logout-warning')

async function signInDestination() {
  try {
    let identity
    try {
      identity = await currentIdentity()
    } catch (error) {
      if (
        !(error instanceof ApiError) ||
        error.code !== 'identity_not_provisioned'
      )
        throw error
      try {
        identity = await (
          await apiFetch('/identity/me/registration', {
            method: 'POST',
            accessToken: await accessToken(),
          })
        ).json()
      } catch {
        throw new Error(
          'Your patient account could not be prepared. Verify your email and try signing in again. If this continues, contact your clinic.',
        )
      }
    }
    const destination = sessionStorage.getItem('telelink.after-sign-in')
    sessionStorage.removeItem('telelink.after-sign-in')
    return destination === '/register-clinic'
      ? destination
      : defaultWorkspace(identity)
  } catch (error) {
    if (error instanceof Error && !(error instanceof ApiError)) throw error
    return '/'
  }
}

export function AuthControls({
  onSessionChange,
  presentation = 'inline',
}: {
  onSessionChange?: (session: Session | null) => void
  presentation?: 'inline' | 'page'
}) {
  const queryClient = useQueryClient()
  const [session, setSession] = useState(readSession)
  const observedSession = useRef(session)
  const [message, setMessage] = useState(logoutWarning)
  const [busy, setBusy] = useState(false)
  useEffect(() => {
    onSessionChange?.(session)
  }, [session, onSessionChange])

  useEffect(
    () => subscribeToSession(() => {
      const next = readSession()
      const previous = observedSession.current
      if (JSON.stringify(next) === JSON.stringify(previous)) return
      observedSession.current = next
      if (next?.refreshToken !== previous?.refreshToken) queryClient.clear()
      setSession(next)
      setMessage('')
    }),
    [queryClient],
  )

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
        return signInDestination().then((destination) => {
          if (!cancelled && destination !== '/') location.replace(destination)
        })
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
        if (!cancelled) {
          const current = readSession()
          if (current?.accessToken === session.accessToken)
            signOut('Your session expired. Please sign in again.')
          else setSession(current)
        }
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

  async function handlePasswordSignIn(email: string, password: string) {
    if (!config || busy) return false
    setBusy(true)
    setMessage('')
    try {
      const value = await signInWithPassword(config, email, password)
      queryClient.clear()
      const destination = await signInDestination()
      setSession(value)
      location.assign(destination)
      return true
    } catch (error) {
      clearSession()
      setSession(null)
      setMessage(
        error instanceof Error
          ? error.message
          : 'Unable to sign in. Please try again.',
      )
      setBusy(false)
      return false
    }
  }

  if (presentation === 'page') {
    return (
      <SignInPage
        config={config}
        signedIn={Boolean(session)}
        busy={busy}
        message={message}
        configurationError={
          config
            ? ''
            : configurationError ||
              'Sign-in is not available right now. Please try again later.'
        }
        onSignIn={handlePasswordSignIn}
      />
    )
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
      {!session ? (
        <a
          href="/sign-in"
          className="inline-flex min-h-9 items-center rounded-md bg-primary px-3 text-sm font-medium text-primary-foreground hover:bg-primary/90 focus-visible:outline-2 focus-visible:outline-offset-4"
        >
          Sign in
        </a>
      ) : (
        <Button
          disabled={busy}
          onClick={() => {
            void handleClick()
          }}
        >
          Sign out
        </Button>
      )}
    </div>
  )
}
