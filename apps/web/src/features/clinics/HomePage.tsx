import { ClinicDirectory } from './ClinicDirectory'

export function HomePage() {
  return (
    <div className="mx-auto max-w-6xl">
      <main className="px-5 py-12 sm:px-8 sm:py-16">
        <p className="text-xs font-semibold tracking-widest text-muted-foreground uppercase">
          Connected care
        </p>
        <h1 className="mt-4 max-w-3xl text-4xl leading-tight font-semibold tracking-tight sm:text-6xl">
          Your clinic, wherever you are.
        </h1>
        <p className="mt-4 max-w-2xl text-lg text-muted-foreground">
          A shared home for patients, doctors and clinic teams.
        </p>
        <section id="clinics" className="mt-10">
          <h2 className="text-2xl font-semibold">Explore clinics</h2>
          <ClinicDirectory />
        </section>
      </main>
    </div>
  )
}
