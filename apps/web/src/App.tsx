export default function App() {
  return (
    <div className="site-shell">
      <header className="site-header"><span className="brand">TeleLink Health</span><span className="badge">Prototype preview</span></header>
      <main className="content">
        <p className="eyebrow">Connected care</p>
        <h1>Your clinic, wherever you are.</h1>
        <p className="intro">A shared home for patients, doctors and clinic teams.</p>
        <div className="card-grid">
          {['Patient', 'Doctor', 'Clinic administrator', 'Platform administrator'].map(role => (
            <section className="card" key={role}><h2>{role}</h2><p>Portal pages are coming next.</p></section>
          ))}
        </div>
      </main>
    </div>
  )
}
