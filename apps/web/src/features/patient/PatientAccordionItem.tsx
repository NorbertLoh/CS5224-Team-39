import { useId } from 'react'
import type { ReactNode } from 'react'
import { ChevronDown } from 'lucide-react'

export function PatientAccordionItem({
  title,
  summary,
  open,
  onToggle,
  children,
}: {
  title: ReactNode
  summary: ReactNode
  open: boolean
  onToggle: () => void
  children: ReactNode
}) {
  const id = useId()
  return (
    <article className="py-4">
      <h2>
        <button
          id={`${id}-trigger`}
          type="button"
          aria-expanded={open}
          aria-controls={`${id}-panel`}
          onClick={onToggle}
          className="flex w-full items-start justify-between gap-4 rounded text-left focus-visible:outline-2 focus-visible:outline-offset-4"
        >
          <span className="min-w-0 space-y-1">
            <span className="block font-medium">{title}</span>
            <span className="block text-sm font-normal text-slate-600">
              {summary}
            </span>
          </span>
          <ChevronDown
            aria-hidden="true"
            size={20}
            className={`mt-1 shrink-0 text-slate-500 transition-transform ${open ? 'rotate-180' : ''}`}
          />
        </button>
      </h2>
      <div
        id={`${id}-panel`}
        role="region"
        aria-labelledby={`${id}-trigger`}
        hidden={!open}
      >
        {open && <div className="space-y-4 pt-4">{children}</div>}
      </div>
    </article>
  )
}
