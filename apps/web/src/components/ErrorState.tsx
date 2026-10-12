import { AlertCircle } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { ApiError, isAbortError } from '@/lib/api-client'
import { cn } from '@/lib/utils'

export function ErrorState({ error, onRetry, retrying = false, className }: {
  error: unknown
  onRetry?: () => void
  retrying?: boolean
  className?: string
}) {
  if (isAbortError(error)) return null
  const message = error instanceof ApiError ? error.message : 'Something went wrong. Please try again.'
  return (
    <div role="alert" className={cn('space-y-3 rounded-xl border border-destructive/30 p-4 text-sm', className)}>
      <div className="flex items-start gap-3">
        <AlertCircle aria-hidden="true" className="size-5 shrink-0 text-destructive" />
        <p>{message}</p>
      </div>
      {error instanceof ApiError && error.requestId && (
        <p className="break-all text-xs text-muted-foreground">Reference: {error.requestId}</p>
      )}
      {onRetry && <Button type="button" variant="outline" onClick={onRetry} disabled={retrying}>{retrying ? 'Retrying…' : 'Try again'}</Button>}
    </div>
  )
}
