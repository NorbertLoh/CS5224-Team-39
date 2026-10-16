import { Button } from '@/components/ui/button'

export function ClinicUnavailable() {
  return (
    <main className="mx-auto max-w-xl px-6 py-24">
      <p className="text-sm text-muted-foreground">TeleLink Health</p>
      <h1 className="mt-4 text-3xl font-semibold tracking-tight">Clinic unavailable</h1>
      <p className="mt-3 text-muted-foreground">This clinic could not be found or is not accepting new consultations.</p>
      <Button asChild variant="outline" className="mt-6"><a href="/">Browse clinics</a></Button>
    </main>
  )
}
