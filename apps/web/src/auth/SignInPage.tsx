import { ArrowLeft, ArrowRight, HeartPulse } from 'lucide-react'
import { PasswordSignInForm } from './PasswordSignInForm'
import { SignInStory } from './SignInStory'

interface SignInPageProps {
  signedIn: boolean
  busy: boolean
  message: string
  configurationError: string
  onSignIn: (email: string, password: string) => Promise<void>
  onHostedSignIn: () => void
}

export function SignInPage({
  signedIn,
  busy,
  message,
  configurationError,
  onSignIn,
  onHostedSignIn,
}: SignInPageProps) {
  return (
    <div className="sign-in-page">
      <a href="#sign-in-content" className="sign-in-skip">
        Skip to sign in
      </a>
      <SignInStory />

      <div className="sign-in-main-panel">
        <nav aria-label="Return navigation" className="sign-in-topbar">
          <a href="/">
            <ArrowLeft size={16} aria-hidden="true" /> Back to home
          </a>
          <span>Connected care, made simple.</span>
        </nav>
        <main id="sign-in-content" className="sign-in-content" tabIndex={-1}>
          <span className="sign-in-welcome-icon">
            <HeartPulse size={29} aria-hidden="true" />
          </span>
          <p className="sign-in-eyebrow">Your TeleLink account</p>
          <h1>{signedIn ? 'You’re already signed in.' : 'Welcome back.'}</h1>
          <p className="sign-in-intro">
            {signedIn
              ? 'Head home to choose your workspace and pick up where you left off.'
              : 'A familiar face. Your next appointment. Everything you need to keep your care moving.'}
          </p>

          <div className="sign-in-action-area">
            {signedIn ? (
              <a href="/" className="sign-in-primary">
                Go to your workspace <ArrowRight size={19} aria-hidden="true" />
              </a>
            ) : (
              <PasswordSignInForm
                busy={busy}
                disabled={Boolean(configurationError)}
                noticeId={
                  message || configurationError ? 'sign-in-notice' : undefined
                }
                onSignIn={onSignIn}
                onHostedSignIn={onHostedSignIn}
              />
            )}
            {(configurationError || message) && (
              <p id="sign-in-notice" role="status" className="sign-in-notice">
                {configurationError || message}
              </p>
            )}
          </div>

          <div className="sign-in-account-note">
            <span className="sign-in-account-note-icon">
              <HeartPulse size={20} aria-hidden="true" />
            </span>
            <div>
              <h2>One account. The right workspace.</h2>
              <p>
                Whether you’re here for your own care or your clinic, sign in
                with your existing account.
              </p>
            </div>
          </div>
          <p className="sign-in-browse">
            Just looking around?{' '}
            <a href="/">
              Explore our clinics <ArrowRight size={14} aria-hidden="true" />
            </a>
          </p>
        </main>
        <footer className="sign-in-footer">
          <span>TeleLink Health</span>
          <span>Care, wherever you are.</span>
        </footer>
      </div>
    </div>
  )
}
