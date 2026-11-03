import { Tabs } from 'radix-ui'
import type { ReactNode } from 'react'
import { tabClassName } from '@/lib/tab-styles'

export function CountTabs({
  value,
  onChange,
  items,
  counts,
  label,
  children,
}: {
  value: string
  onChange: (value: string) => void
  items: { value: string; label: string }[]
  counts?: Record<string, number>
  label: string
  children: ReactNode
}) {
  return (
    <Tabs.Root value={value} onValueChange={onChange}>
      <div className="overflow-x-auto">
        <Tabs.List
          aria-label={label}
          className="flex min-w-max gap-2 border-b border-slate-200"
        >
          {items.map((item) => (
            <Tabs.Trigger
              key={item.value}
              value={item.value}
              className={tabClassName(item.value === value)}
            >
              {item.label}
              <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs tabular-nums text-slate-700">
                {counts?.[item.value] ?? '—'}
              </span>
            </Tabs.Trigger>
          ))}
        </Tabs.List>
      </div>
      <Tabs.Content
        key={value}
        value={value}
        className="pt-5 outline-none focus-visible:ring-2 focus-visible:ring-teal-600"
      >
        {children}
      </Tabs.Content>
    </Tabs.Root>
  )
}
