import {
  ArrowRight,
  CalendarDays,
  Check,
  FileText,
  HeartPulse,
  Video,
} from 'lucide-react'

export function SignInStory() {
  return (
    <aside className="sign-in-story" aria-label="About TeleLink Health">
      <a href="/" className="sign-in-brand">
        <span className="sign-in-brand-mark">
          <HeartPulse aria-hidden="true" size={24} />
        </span>
        <span>
          TeleLink<span className="sign-in-brand-light"> Health</span>
        </span>
      </a>
      <div className="sign-in-story-body">
        <p className="sign-in-eyebrow">
          <span /> Care that stays connected
        </p>
        <h2>
          Your care.
          <br /> All connected.
        </h2>
        <p className="sign-in-story-description">
          From your first appointment to your next step.
          <br className="sign-in-desktop-break" /> A little less admin. More
          room for care.
        </p>
        <div className="sign-in-journey" aria-hidden="true">
          <div className="sign-in-journey-line" />
          <div className="sign-in-journey-card">
            <span className="sign-in-journey-icon">
              <CalendarDays size={21} />
            </span>
            <div>
              <small>01 / MAKE TIME FOR YOU</small>
              <strong>Find your clinic</strong>
              <span>Book a time that works for you.</span>
            </div>
            <Check size={17} className="sign-in-journey-check" />
          </div>
          <div className="sign-in-journey-card sign-in-journey-card-middle">
            <span className="sign-in-journey-icon">
              <Video size={21} />
            </span>
            <div>
              <small>02 / CONNECT FROM ANYWHERE</small>
              <strong>Meet your doctor</strong>
              <span>Your consultation, over video.</span>
            </div>
            <span className="sign-in-live-dot" />
          </div>
          <div className="sign-in-journey-card">
            <span className="sign-in-journey-icon">
              <FileText size={21} />
            </span>
            <div>
              <small>03 / KEEP EVERYTHING TOGETHER</small>
              <strong>Take the next step</strong>
              <span>Access your documents and prescriptions.</span>
            </div>
            <ArrowRight size={17} className="sign-in-journey-check" />
          </div>
        </div>
      </div>
      <p className="sign-in-story-footer">
        One place for patients, doctors and clinic teams.
      </p>
    </aside>
  )
}
