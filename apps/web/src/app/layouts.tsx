import { Link, NavLink, Outlet } from 'react-router'
import { portals } from './portals'
import type { PortalRole } from './portals'
import { pagesFor } from '../features/registry'

export function RootLayout() {
  return <div className="site-shell">
    <a className="skip-link" href="#main-content">Skip to content</a>
    <header className="site-header"><Link className="brand" to="/">TeleLink Health</Link><Link to="/">Portals</Link><span className="badge">Prototype preview</span></header>
    <Outlet />
  </div>
}

export function PortalLayout({ role }: { role: PortalRole }) {
  return <div className="portal-shell">
    <aside className="portal-sidebar"><h2>{portals[role].title}</h2>
      <nav aria-label={`${portals[role].title} navigation`}>
        <NavLink to={`/${role}`} end>Overview</NavLink>
        {pagesFor(role).filter(page => page.navigation !== false).map(page => (
          <NavLink key={page.path} to={`/${role}/${page.path}`}>{page.label}</NavLink>
        ))}
      </nav>
    </aside>
    <main id="main-content" className="portal-content"><Outlet /></main>
  </div>
}

export function PortalOverview({ role }: { role: PortalRole }) {
  return <><p className="eyebrow">Overview</p><h1>{portals[role].title}</h1><p className="intro">{portals[role].description}</p><p>Choose a page from the navigation to explore the prototype.</p></>
}
