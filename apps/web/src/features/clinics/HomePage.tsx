import { useState } from 'react'
import { AuthControls } from '@/auth/AuthControls'
import { readSession } from '@/auth/session'
import { ClinicDirectory } from './ClinicDirectory'
import { ManagedClinics } from './ManagedClinics'

export function HomePage() {
  const [session, setSession] = useState(readSession)
  return <div className="mx-auto max-w-6xl">
    <header className="flex flex-wrap items-center justify-between gap-4 border-b px-5 py-6 sm:px-8"><span className="text-xl font-semibold tracking-tight">TeleLink Health</span><AuthControls onSessionChange={setSession} /></header>
    <main className="px-5 py-12 sm:px-8 sm:py-16">
      <p className="text-xs font-semibold tracking-widest text-muted-foreground uppercase">Connected care</p>
      <h1 className="mt-4 max-w-3xl text-4xl leading-tight font-semibold tracking-tight sm:text-6xl">Your clinic, wherever you are.</h1>
      <p className="mt-4 max-w-2xl text-lg text-muted-foreground">A shared home for patients, doctors and clinic teams.</p>
      <section className="mt-10"><h2 className="text-2xl font-semibold">Explore clinics</h2><ClinicDirectory /></section>
      {session && <ManagedClinics session={session} />}
    </main>
  </div>
}
