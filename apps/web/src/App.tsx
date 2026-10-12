import { Link } from 'react-router'
import { portals } from './app/portals'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardFooter, CardHeader, CardTitle } from '@/components/ui/card'

export default function App() {
  return (
    <main id="main-content" className="px-5 py-12 sm:px-8 sm:py-16">
      <p className="text-xs font-semibold tracking-widest text-muted-foreground uppercase">Connected care</p>
      <h1 className="mt-4 max-w-3xl text-4xl leading-tight font-semibold tracking-tight sm:text-6xl">Your clinic, wherever you are.</h1>
      <p className="mt-4 max-w-2xl text-lg text-muted-foreground">A shared home for patients, doctors and clinic teams.</p>
      <div className="mt-10 grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
        {Object.entries(portals).map(([role, portal]) => (
          <Card key={role}>
            <CardHeader><CardTitle><h2>{portal.title}</h2></CardTitle></CardHeader>
            <CardContent className="grow"><p className="text-muted-foreground">{portal.description}</p></CardContent>
            <CardFooter>
              <Button asChild variant="outline" className="h-auto min-h-9 w-full whitespace-normal text-center">
                <Link to={`/${role}`}>Open {portal.title.toLowerCase()}</Link>
              </Button>
            </CardFooter>
          </Card>
        ))}
      </div>
      <Button asChild variant="link" className="mt-6 px-0"><Link to="/clinics/demo">Explore a clinic storefront</Link></Button>
    </main>
  )
}
