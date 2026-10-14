import { AppShell } from './navigation/AppShell'
import { AppRoutes } from './navigation/AppRoutes'
import { parseRoute } from './navigation/access'

export default function App() {
  const route = parseRoute(window.location.pathname)
  return <AppShell route={route}>{session => <AppRoutes route={route} session={session} />}</AppShell>
}
