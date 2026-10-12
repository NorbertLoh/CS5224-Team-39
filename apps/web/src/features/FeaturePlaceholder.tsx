import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'

export function FeaturePlaceholder({ title }: { title: string }) {
  return (
    <Card>
      <CardHeader>
        <p className="text-xs font-semibold tracking-widest text-muted-foreground uppercase">Coming next</p>
        <CardTitle><h1 className="text-3xl font-semibold tracking-tight">{title}</h1></CardTitle>
      </CardHeader>
      <CardContent><p className="text-muted-foreground">This page is reserved for the next stage of the prototype.</p></CardContent>
    </Card>
  )
}
