import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { AuthControls } from './auth/AuthControls'

export default function App() {
  return (
    <div className="mx-auto max-w-6xl">
      <header className="flex flex-wrap items-center justify-between gap-4 border-b px-5 py-6 sm:px-8">
        <span className="text-xl font-semibold tracking-tight">TeleLink Health</span>
        <Badge variant="secondary">Prototype preview</Badge>
        <AuthControls />
      </header>
      <main className="px-5 py-12 sm:px-8 sm:py-16">
        <p className="text-xs font-semibold tracking-widest text-muted-foreground uppercase">Connected care</p>
        <h1 className="mt-4 max-w-3xl text-4xl leading-tight font-semibold tracking-tight sm:text-6xl">Your clinic, wherever you are.</h1>
        <p className="mt-4 max-w-2xl text-lg text-muted-foreground">A shared home for patients, doctors and clinic teams.</p>
        <div className="mt-10 grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
          {['Patient', 'Doctor', 'Clinic administrator', 'Platform administrator'].map(role => (
            <Card key={role}>
              <CardHeader><CardTitle><h2>{role}</h2></CardTitle></CardHeader>
              <CardContent><p className="text-muted-foreground">Portal pages are coming next.</p></CardContent>
            </Card>
          ))}
        </div>
      </main>
    </div>
  )
}
