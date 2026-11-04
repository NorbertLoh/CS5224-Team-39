import { cn } from '@/lib/utils'
import { LoaderCircle } from 'lucide-react'

export function LoadingState({
  message = 'Loading…',
  className,
}: {
  message?: string
  className?: string
}) {
  return (
    <div
      role="status"
      aria-live="polite"
      aria-busy="true"
      className={cn(
        'flex items-center gap-3 p-4 text-sm text-muted-foreground',
        className,
      )}
    >
      <LoaderCircle
        aria-hidden="true"
        className="size-5 animate-spin motion-reduce:animate-none"
      />
      <span>{message}</span>
    </div>
  )
}
