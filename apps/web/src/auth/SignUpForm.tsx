import { useEffect, useState } from 'react'
import { ArrowLeft, ArrowRight, Eye, EyeOff, LockKeyhole } from 'lucide-react'
import type { AuthConfig } from './session'
import { confirmSignUp, resendSignUpCode, signUp } from './registration'

export function SignUpForm({
  config,
  onReturn,
}: {
  config: AuthConfig | null
  onReturn: (message?: string) => void
}) {
  const [step, setStep] = useState<'details' | 'verify'>('details')
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirmation, setConfirmation] = useState('')
  const [code, setCode] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [cooldown, setCooldown] = useState(0)

  useEffect(() => {
    if (!cooldown) return
    const timer = window.setTimeout(
      () => setCooldown((value) => value - 1),
      1000,
    )
    return () => clearTimeout(timer)
  }, [cooldown])

  async function perform(action: 'submit' | 'resend') {
    if (!config || busy) return
    if (step === 'details' && password !== confirmation) {
      setMessage('Your passwords do not match.')
      return
    }
    setBusy(true)
    setMessage('')
    try {
      if (action === 'resend') {
        await resendSignUpCode(config, email)
        setCooldown(60)
        setMessage(
          'A new verification code has been requested. Check your email.',
        )
      } else if (step === 'details') {
        const confirmed = await signUp(config, name, email, password)
        setPassword('')
        setConfirmation('')
        if (confirmed) onReturn('Account created. Sign in to continue.')
        else {
          setStep('verify')
          setCooldown(60)
          setMessage('Check your email for your verification code.')
        }
      } else {
        await confirmSignUp(config, email, code)
        onReturn('Email verified. Sign in to start using your account.')
      }
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Please try again.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <form
      aria-label={step === 'details' ? 'Create account' : 'Verify email'}
      aria-describedby="sign-up-notice"
      onSubmit={(event) => {
        event.preventDefault()
        void perform('submit')
      }}
    >
      <fieldset disabled={busy || !config} className="sign-in-fields">
        {step === 'details' && (
          <div className="sign-in-field">
            <label htmlFor="sign-up-name">Full name</label>
            <input
              id="sign-up-name"
              name="name"
              autoComplete="name"
              required
              maxLength={200}
              pattern=".*\S.*"
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="Your full name"
            />
          </div>
        )}
        <div className="sign-in-field">
          <label htmlFor="sign-up-email">Email address</label>
          <input
            id="sign-up-email"
            name="email"
            type="email"
            autoComplete="email"
            autoCapitalize="none"
            spellCheck={false}
            required
            value={email}
            onChange={(event) => {
              setEmail(event.target.value)
              setCode('')
            }}
            placeholder="you@example.com"
          />
        </div>
        {step === 'details' ? (
          <>
            <div className="sign-in-field">
              <label htmlFor="sign-up-password">Password</label>
              <div className="sign-in-password-wrap">
                <input
                  id="sign-up-password"
                  name="password"
                  type={showPassword ? 'text' : 'password'}
                  autoComplete="new-password"
                  required
                  minLength={8}
                  maxLength={256}
                  aria-describedby="sign-up-password-hint"
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                />
                <button
                  type="button"
                  className="sign-in-password-toggle"
                  aria-label={showPassword ? 'Hide password' : 'Show password'}
                  aria-pressed={showPassword}
                  onClick={() => setShowPassword((value) => !value)}
                >
                  {showPassword ? (
                    <EyeOff size={18} aria-hidden="true" />
                  ) : (
                    <Eye size={18} aria-hidden="true" />
                  )}
                </button>
              </div>
              <p id="sign-up-password-hint" className="sign-up-hint">
                Use at least 8 characters, with uppercase and lowercase letters,
                a number and a symbol.
              </p>
            </div>
            <div className="sign-in-field">
              <label htmlFor="sign-up-confirmation">Confirm password</label>
              <input
                id="sign-up-confirmation"
                name="password-confirmation"
                type={showPassword ? 'text' : 'password'}
                autoComplete="new-password"
                required
                minLength={8}
                maxLength={256}
                value={confirmation}
                onChange={(event) => setConfirmation(event.target.value)}
              />
            </div>
          </>
        ) : (
          <div className="sign-in-field">
            <label htmlFor="sign-up-code">Verification code</label>
            <input
              id="sign-up-code"
              name="code"
              autoComplete="one-time-code"
              required
              maxLength={2048}
              value={code}
              onChange={(event) => setCode(event.target.value)}
              placeholder="Enter the code from your email"
            />
          </div>
        )}
        <button type="submit" className="sign-in-primary" aria-busy={busy}>
          {busy
            ? 'Please wait…'
            : step === 'details'
              ? 'Create account'
              : 'Verify email'}{' '}
          <ArrowRight size={19} aria-hidden="true" />
        </button>
        {step === 'verify' && (
          <button
            type="button"
            className="sign-in-hosted"
            disabled={cooldown > 0}
            onClick={(event) => {
              const input = event.currentTarget.form?.elements.namedItem(
                'email',
              ) as HTMLInputElement | null
              if (input?.reportValidity()) void perform('resend')
            }}
          >
            {cooldown > 0
              ? `Resend code in ${cooldown}s`
              : 'Resend verification code'}
          </button>
        )}
      </fieldset>
      <p
        id="sign-up-notice"
        role="status"
        className={message ? 'sign-in-notice' : 'sign-up-hint'}
      >
        {message}
      </p>
      {step === 'details' && (
        <p className="sign-in-explanation">
          <LockKeyhole size={15} aria-hidden="true" /> Your account gives you
          access to patient care.
        </p>
      )}
      <button
        type="button"
        className="sign-in-hosted"
        disabled={busy}
        onClick={() => onReturn()}
      >
        <ArrowLeft size={14} aria-hidden="true" /> Back to sign in
      </button>
    </form>
  )
}
