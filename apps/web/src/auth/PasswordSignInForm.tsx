import { ArrowRight, Eye, EyeOff, LockKeyhole } from 'lucide-react'
import { useState } from 'react'

interface PasswordSignInFormProps {
  busy: boolean
  disabled: boolean
  noticeId?: string
  onSignIn: (email: string, password: string) => Promise<boolean>
}

export function PasswordSignInForm({
  busy,
  disabled,
  noticeId,
  onSignIn,
}: PasswordSignInFormProps) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)

  async function submit() {
    try {
      await onSignIn(email, password)
    } finally {
      setPassword('')
    }
  }
  return (
    <form
      onSubmit={(event) => {
        event.preventDefault()
        if (!busy) void submit()
      }}
      aria-label="Sign in"
      aria-describedby={noticeId}
    >
      <fieldset disabled={busy || disabled} className="sign-in-fields">
        <div className="sign-in-field">
          <label htmlFor="sign-in-email">Email address</label>
          <input
            id="sign-in-email"
            name="username"
            type="email"
            autoComplete="username"
            autoCapitalize="none"
            spellCheck={false}
            required
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            placeholder="you@example.com"
          />
        </div>
        <div className="sign-in-field">
          <label htmlFor="sign-in-password">Password</label>
          <div className="sign-in-password-wrap">
            <input
              id="sign-in-password"
              name="password"
              type={showPassword ? 'text' : 'password'}
              autoComplete="current-password"
              required
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
        </div>
        <button type="submit" className="sign-in-primary" aria-busy={busy}>
          {busy ? 'Signing in…' : 'Sign in'}{' '}
          <ArrowRight size={19} aria-hidden="true" />
        </button>
      </fieldset>
      <p className="sign-in-explanation">
        <LockKeyhole size={15} aria-hidden="true" /> Secure sign-in to your
        TeleLink account.
      </p>
    </form>
  )
}
