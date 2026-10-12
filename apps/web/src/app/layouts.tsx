import { Link, NavLink, Outlet } from 'react-router'
import { Badge } from '@/components/ui/badge'
import { Button, buttonVariants } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { portals } from './portals'
import type { PortalRole } from './portals'
import { pagesFor } from '../features/registry'

export function RootLayout() {
  return (
    <div className="mx-auto max-w-6xl">
      <a className="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-5 focus:z-10 focus:rounded focus:bg-background focus:p-2" href="#main-content">Skip to content</a>
      <header className="flex flex-wrap items-center justify-between gap-4 border-b px-5 py-6 sm:px-8">
        <Link className="rounded text-xl font-semibold tracking-tight focus-visible:ring-2 focus-visible:ring-ring" to="/">TeleLink Health</Link>
        <Button asChild variant="ghost"><Link to="/">Portals</Link></Button>
        <Badge variant="secondary">Prototype preview</Badge>
      </header>
      <Outlet />
    </div>
  )
}

export function PortalLayout({ role }: { role: PortalRole }) {
  const navigationClass = ({ isActive }: { isActive: boolean }) => cn(
    buttonVariants({ variant: isActive ? 'secondary' : 'ghost' }),
    'h-auto min-h-9 w-full justify-start whitespace-normal',
  )
  return (
    <div className="grid md:grid-cols-[260px_minmax(0,1fr)]">
      <aside className="border-b p-5 md:border-r md:border-b-0 md:p-6">
        <h2 className="mb-4 text-lg font-semibold">{portals[role].title}</h2>
        <nav className="grid grid-cols-2 gap-2 md:grid-cols-1" aria-label={`${portals[role].title} navigation`}>
          <NavLink className={navigationClass} to={`/${role}`} end>Overview</NavLink>
          {pagesFor(role).filter(page => page.navigation !== false).map(page => (
            <NavLink className={navigationClass} key={page.path} to={`/${role}/${page.path}`}>{page.label}</NavLink>
          ))}
        </nav>
      </aside>
      <main id="main-content" className="min-w-0 px-5 py-10 sm:px-8"><Outlet /></main>
    </div>
  )
}

export function PortalOverview({ role }: { role: PortalRole }) {
  return (
    <div className="space-y-4">
      <p className="text-xs font-semibold tracking-widest text-muted-foreground uppercase">Overview</p>
      <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">{portals[role].title}</h1>
      <p className="text-lg text-muted-foreground">{portals[role].description}</p>
      <p>Choose a page from the navigation to explore the prototype.</p>
    </div>
  )
}
