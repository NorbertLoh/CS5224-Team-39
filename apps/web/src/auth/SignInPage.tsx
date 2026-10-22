import { useState } from 'react'
import { ArrowLeft, ArrowRight, CalendarDays, Check, Eye, EyeOff, FileText, HeartPulse, LockKeyhole, Video } from 'lucide-react'

interface SignInPageProps {
  signedIn: boolean
  busy: boolean
  message: string
  configurationError: string
  onSignIn: (email: string, password: string) => Promise<void>
  onHostedSignIn: () => void
}

export function SignInPage({ signedIn, busy, message, configurationError, onSignIn, onHostedSignIn }: SignInPageProps) {
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
    <div className="sign-in-page">
      <a href="#sign-in-content" className="sign-in-skip">Skip to sign in</a>
      <aside className="sign-in-story" aria-label="About TeleLink Health">
        <a href="/" className="sign-in-brand">
          <span className="sign-in-brand-mark"><HeartPulse aria-hidden="true" size={24} /></span>
          <span>TeleLink<span className="sign-in-brand-light"> Health</span></span>
        </a>
        <div className="sign-in-story-body">
          <p className="sign-in-eyebrow"><span /> Care that stays connected</p>
          <h2>Your care.<br />{' '}All connected.</h2>
          <p className="sign-in-story-description">From your first appointment to your next step.<br className="sign-in-desktop-break" /> A little less admin. More room for care.</p>
          <div className="sign-in-journey" aria-hidden="true">
            <div className="sign-in-journey-line" />
            <div className="sign-in-journey-card">
              <span className="sign-in-journey-icon"><CalendarDays size={21} /></span>
              <div><small>01 / MAKE TIME FOR YOU</small><strong>Find your clinic</strong><span>Book a time that works for you.</span></div>
              <Check size={17} className="sign-in-journey-check" />
            </div>
            <div className="sign-in-journey-card sign-in-journey-card-middle">
              <span className="sign-in-journey-icon"><Video size={21} /></span>
              <div><small>02 / CONNECT FROM ANYWHERE</small><strong>Meet your doctor</strong><span>Your consultation, over video.</span></div>
              <span className="sign-in-live-dot" />
            </div>
            <div className="sign-in-journey-card">
              <span className="sign-in-journey-icon"><FileText size={21} /></span>
              <div><small>03 / KEEP EVERYTHING TOGETHER</small><strong>Take the next step</strong><span>Access your documents and prescriptions.</span></div>
              <ArrowRight size={17} className="sign-in-journey-check" />
            </div>
          </div>
        </div>
        <p className="sign-in-story-footer">One place for patients, doctors and clinic teams.</p>
      </aside>

      <div className="sign-in-main-panel">
        <nav aria-label="Return navigation" className="sign-in-topbar">
          <a href="/"><ArrowLeft size={16} aria-hidden="true" /> Back to home</a>
          <span>Connected care, made simple.</span>
        </nav>
        <main id="sign-in-content" className="sign-in-content" tabIndex={-1}>
          <span className="sign-in-welcome-icon"><HeartPulse size={29} aria-hidden="true" /></span>
          <p className="sign-in-eyebrow">Your TeleLink account</p>
          <h1>{signedIn ? 'You’re already signed in.' : 'Welcome back.'}</h1>
          <p className="sign-in-intro">{signedIn ? 'Head home to choose your workspace and pick up where you left off.' : 'A familiar face. Your next appointment. Everything you need to keep your care moving.'}</p>

          <div className="sign-in-action-area">
            {signedIn ? (
              <a href="/" className="sign-in-primary">Go to your workspace <ArrowRight size={19} aria-hidden="true" /></a>
            ) : (
              <form onSubmit={event => { event.preventDefault(); if (!busy) void submit() }} aria-label="Sign in" aria-describedby={message || configurationError ? 'sign-in-notice' : undefined}>
                <fieldset disabled={busy || Boolean(configurationError)} className="sign-in-fields">
                  <div className="sign-in-field">
                    <label htmlFor="sign-in-email">Email address</label>
                    <input id="sign-in-email" name="username" type="email" autoComplete="username" autoCapitalize="none" spellCheck={false} required value={email} onChange={event => setEmail(event.target.value)} placeholder="you@example.com" />
                  </div>
                  <div className="sign-in-field">
                    <label htmlFor="sign-in-password">Password</label>
                    <div className="sign-in-password-wrap">
                      <input id="sign-in-password" name="password" type={showPassword ? 'text' : 'password'} autoComplete="current-password" required value={password} onChange={event => setPassword(event.target.value)} />
                      <button type="button" className="sign-in-password-toggle" aria-label={showPassword ? 'Hide password' : 'Show password'} aria-pressed={showPassword} onClick={() => setShowPassword(value => !value)}>{showPassword ? <EyeOff size={18} aria-hidden="true" /> : <Eye size={18} aria-hidden="true" />}</button>
                    </div>
                  </div>
                  <button type="submit" className="sign-in-primary" aria-busy={busy}>
                    {busy ? 'Signing in…' : 'Sign in'} <ArrowRight size={19} aria-hidden="true" />
                  </button>
                </fieldset>
                <p className="sign-in-explanation"><LockKeyhole size={15} aria-hidden="true" /> Secure sign-in to your TeleLink account.</p>
                <button type="button" className="sign-in-hosted" onClick={onHostedSignIn} disabled={busy || Boolean(configurationError)}>More sign-in options <ArrowRight size={14} aria-hidden="true" /></button>
              </form>
            )}
            {(configurationError || message) && <p id="sign-in-notice" role="status" className="sign-in-notice">{configurationError || message}</p>}
          </div>

          <div className="sign-in-account-note">
            <span className="sign-in-account-note-icon"><HeartPulse size={20} aria-hidden="true" /></span>
            <div><h2>One account. The right workspace.</h2><p>Whether you’re here for your own care or your clinic, sign in with your existing account.</p></div>
          </div>
          <p className="sign-in-browse">Just looking around? <a href="/">Explore our clinics <ArrowRight size={14} aria-hidden="true" /></a></p>
        </main>
        <footer className="sign-in-footer"><span>TeleLink Health</span><span>Care, wherever you are.</span></footer>
      </div>
    </div>
  )
}
