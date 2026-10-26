import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { AlertCircle } from 'lucide-react'

export function ErrorState({
  message = 'Something went wrong. Please try again.',
  onRetry,
  retrying = false,
  className,
}: {
  message?: string
  onRetry?: () => void
  retrying?: boolean
  className?: string
}) {
  return (
    <div
      role="alert"
      className={cn(
        'space-y-3 rounded-xl border border-destructive/30 p-4 text-sm',
        className,
      )}
    >
      <div className="flex items-start gap-3">
        <AlertCircle
          aria-hidden="true"
          className="size-5 shrink-0 text-destructive"
        />
        <p>{message}</p>
      </div>
      {onRetry && (
        <Button
          type="button"
          variant="outline"
          onClick={onRetry}
          disabled={retrying}
        >
          {retrying ? 'Retrying…' : 'Try again'}
        </Button>
      )}
    </div>
  )
}
