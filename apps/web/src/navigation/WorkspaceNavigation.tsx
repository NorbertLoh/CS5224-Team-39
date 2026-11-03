import type { ReactNode } from 'react'
import type { LucideIcon } from 'lucide-react'
import { tabClassName } from '@/lib/tab-styles'
import type { NavigationAttention } from '@/navigation/attention'

export type WorkspaceLink = {
  href: string
  label: string
  active: boolean
  icon?: LucideIcon
  attention?: NavigationAttention
}

export function WorkspaceNavigation({
  title,
  description,
  icon: Icon,
  links,
  children,
}: {
  title: string
  description: string
  icon: LucideIcon
  links: WorkspaceLink[]
  children?: ReactNode
}) {
  return (
    <div className="border-t border-slate-100 bg-slate-50/70">
      <div className="mx-auto max-w-6xl px-4 py-3 sm:px-6">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex min-w-0 items-center gap-3">
            <span className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-teal-100 text-teal-800">
              <Icon size={21} aria-hidden="true" />
            </span>
            <div className="min-w-0">
              <p className="text-sm font-semibold text-slate-900">{title}</p>
              <p className="text-xs text-slate-500">{description}</p>
            </div>
          </div>
          {children}
        </div>
        <nav
          aria-label={title}
          className="mt-3 flex gap-1 overflow-x-auto border-b border-slate-200"
        >
          {links.map(({ href, label, active, attention, icon: LinkIcon }) => (
            <a
              key={href}
              href={href}
              aria-current={active ? 'page' : undefined}
              className={tabClassName(active, attention?.tone)}
            >
              {LinkIcon && (
                <LinkIcon
                  size={17}
                  className="hidden sm:block"
                  aria-hidden="true"
                />
              )}
              {label}
              {attention && (
                <span
                  title={attention.description}
                  className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-semibold ${attention.tone === 'danger' ? 'bg-red-100 text-red-800' : 'bg-amber-100 text-amber-900'}`}
                >
                  {attention.label}
                  {attention.count !== undefined && <> · {attention.count}</>}
                  <span className="sr-only">. {attention.description}</span>
                </span>
              )}
            </a>
          ))}
        </nav>
      </div>
    </div>
  )
}
