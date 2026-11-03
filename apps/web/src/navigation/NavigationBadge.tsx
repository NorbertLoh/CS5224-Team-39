import type { NavigationAttention } from '@/navigation/attention'

export function NavigationBadge({
  attention,
}: {
  attention: NavigationAttention
}) {
  return (
    <span
      title={attention.description}
      className={`inline-flex min-w-5 items-center justify-center rounded-full px-1.5 py-0.5 text-xs font-semibold tabular-nums ${attention.tone === 'danger' ? 'bg-red-100 text-red-800' : 'bg-amber-100 text-amber-900'}`}
    >
      <span aria-hidden="true">{attention.count ?? 1}</span>
      <span className="sr-only">
        {attention.label}: {attention.count ?? 1}. {attention.description}
      </span>
    </span>
  )
}
