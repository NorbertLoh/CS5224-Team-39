import { Link } from 'react-router'
import { portals } from './app/portals'

export default function App() {
  return (
      <main id="main-content" className="content">
        <p className="eyebrow">Connected care</p>
        <h1>Your clinic, wherever you are.</h1>
        <p className="intro">A shared home for patients, doctors and clinic teams.</p>
        <div className="card-grid">
          {Object.entries(portals).map(([role, portal]) => (
            <section className="card" key={role}><h2>{portal.title}</h2><p>{portal.description}</p><Link to={`/${role}`}>Open {portal.title.toLowerCase()}</Link></section>
          ))}
        </div>
        <p><Link to="/clinics/demo">Explore a clinic storefront</Link></p>
      </main>
  )
}
